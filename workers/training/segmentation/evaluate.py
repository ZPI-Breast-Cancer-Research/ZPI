"""Score predicted masks against the ground truth: Dice and HD95 per case, means per group.

One script for every model, so results of different models and settings are comparable (SEG-9).

Empty masks:
- both empty: Dice 1.0, HD95 0.0
- only one empty: Dice 0.0, HD95 NaN (left out of the HD95 mean, counted in `n`)
"""

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage

STATUSES = ("ok", "empty_pred", "empty_gt", "both_empty", "missing")
GROUP_COLUMNS = ("collection", "size_bin_eval")
FILE_ENDING = ".nii.gz"
PER_CASE_COLUMNS = ("case_id", "collection", "size_bin_eval", "dice", "hd95", "status")
DIGITS = 4


@dataclass(frozen=True)
class CaseInfo:
    case_id: str
    collection: str
    size_bin_eval: str


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    collection: str
    size_bin_eval: str
    dice: float | None  # None when the prediction is missing
    hd95: float | None  # None when missing, NaN when only one mask is empty
    status: str  # one of STATUSES


def read_case_info(split_csv: Path) -> dict[str, CaseInfo]:
    """case_id -> collection and size bin, from frozen_split_official.csv."""
    with split_csv.open(newline="", encoding="utf-8") as f:
        return {
            row["patient_id"]: CaseInfo(row["patient_id"], row["collection"], row["size_bin_eval"])
            for row in csv.DictReader(f)
        }


def load_mask(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return the mask as a bool array and its affine."""
    image = nib.load(path)
    return np.asanyarray(image.dataobj) > 0, image.affine


def check_geometry(case_id: str, pred_affine, gt_affine, pred_shape, gt_shape) -> None:
    """Raise ValueError naming the case if shape or affine differ."""
    if tuple(pred_shape) != tuple(gt_shape):
        raise ValueError(
            f"{case_id}: prediction shape {tuple(pred_shape)} != ground truth {tuple(gt_shape)}"
        )
    if not np.allclose(pred_affine, gt_affine, atol=1e-4):
        raise ValueError(f"{case_id}: prediction affine differs from the ground truth")


def dice(pred: np.ndarray, gt: np.ndarray) -> float:
    """Dice of two bool masks; both empty -> 1.0."""
    total = int(pred.sum()) + int(gt.sum())
    if total == 0:
        return 1.0
    return 2 * int(np.logical_and(pred, gt).sum()) / total


def _surface(mask: np.ndarray) -> np.ndarray:
    # voxels of the mask with a neighbour outside it; the volume border counts as outside
    return mask & ~ndimage.binary_erosion(mask, border_value=0)


def hd95(pred: np.ndarray, gt: np.ndarray, spacing: tuple[float, ...]) -> float:
    """95th percentile of surface-to-surface distances in both directions, in mm.

    Both masks must be non-empty; the empty-mask rule lives in evaluate_case.
    """
    if not pred.any() or not gt.any():
        raise ValueError("hd95 needs two non-empty masks")
    # Distances only depend on the two surfaces, so work inside their bounding box (one voxel of
    # margin keeps the volume border the only border a mask can touch): same result, much faster.
    nonzero = np.argwhere(pred | gt)
    low = np.maximum(nonzero.min(axis=0) - 1, 0)
    high = nonzero.max(axis=0) + 2
    box = tuple(slice(lo, hi) for lo, hi in zip(low, high, strict=True))
    pred, gt = pred[box], gt[box]
    pred_surface, gt_surface = _surface(pred), _surface(gt)
    # distance of every voxel to the nearest surface voxel of the other mask
    to_gt = ndimage.distance_transform_edt(~gt_surface, sampling=spacing)
    to_pred = ndimage.distance_transform_edt(~pred_surface, sampling=spacing)
    distances = np.concatenate([to_gt[pred_surface], to_pred[gt_surface]])
    return float(np.percentile(distances, 95))


def evaluate_case(
    case_id: str, pred_path: Path | None, gt_path: Path, info: CaseInfo
) -> CaseResult:
    """Score one case, following the empty-mask rule in the module docstring."""

    def result(dice_: float | None, hd95_: float | None, status: str) -> CaseResult:
        return CaseResult(case_id, info.collection, info.size_bin_eval, dice_, hd95_, status)

    if pred_path is None:
        return result(None, None, "missing")
    pred, pred_affine = load_mask(pred_path)
    gt, gt_affine = load_mask(gt_path)
    check_geometry(case_id, pred_affine, gt_affine, pred.shape, gt.shape)

    if not pred.any() and not gt.any():
        return result(1.0, 0.0, "both_empty")
    if not pred.any():
        return result(0.0, float("nan"), "empty_pred")
    if not gt.any():
        return result(0.0, float("nan"), "empty_gt")
    spacing = tuple(float(v) for v in nib.affines.voxel_sizes(gt_affine))
    return result(dice(pred, gt), hd95(pred, gt, spacing), "ok")


def read_fold_cases(splits_json: Path, fold: int) -> set[str]:
    """Validation cases of one fold, from nnU-Net's splits_final.json."""
    return set(json.loads(splits_json.read_text(encoding="utf-8"))[fold]["val"])


def evaluate(
    pred_dir: Path, gt_dir: Path, cases: dict[str, CaseInfo], only: set[str] | None = None
) -> list[CaseResult]:
    """Score every ground-truth case in gt_dir (or those in `only`), sorted by case_id.

    A case without a prediction is reported as missing.
    """
    results = []
    for gt_path in sorted(gt_dir.glob(f"*{FILE_ENDING}")):
        case_id = gt_path.name.removesuffix(FILE_ENDING)
        if only is not None and case_id not in only:
            continue
        if case_id not in cases:
            raise ValueError(f"{case_id}: not in the split file")
        pred_path = pred_dir / gt_path.name
        results.append(
            evaluate_case(
                case_id, pred_path if pred_path.exists() else None, gt_path, cases[case_id]
            )
        )
    return results


def _round(value: float | None) -> float | None:
    return None if value is None or np.isnan(value) else round(float(value), DIGITS)


def _group_stats(results: list[CaseResult]) -> dict:
    scored = [r for r in results if r.status != "missing"]
    hd = [r.hd95 for r in scored if not np.isnan(r.hd95)]
    return {
        "n": len(results),
        "n_missing": len(results) - len(scored),
        "n_hd95": len(hd),  # cases with only one empty mask have no HD95
        "dice_mean": _round(float(np.mean([r.dice for r in scored]))) if scored else None,
        "hd95_mean": _round(float(np.mean(hd))) if hd else None,
    }


def summarize(results: list[CaseResult]) -> dict:
    """Means overall, per collection and per size bin, each with n; plus the missing cases."""
    summary = {
        "overall": _group_stats(results),
        "statuses": {status: sum(r.status == status for r in results) for status in STATUSES},
        "missing": sorted(r.case_id for r in results if r.status == "missing"),
    }
    for column in GROUP_COLUMNS:
        groups = sorted({getattr(r, column) for r in results})
        summary[column] = {
            group: _group_stats([r for r in results if getattr(r, column) == group])
            for group in groups
        }
    return summary


def write_per_case(results: list[CaseResult], out: Path) -> None:
    """One row per case; empty cells for a missing case, "nan" for HD95 with one empty mask."""

    def cell(value: float | None) -> str:
        if value is None:
            return ""
        return "nan" if np.isnan(value) else f"{value:.{DIGITS}f}"

    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(PER_CASE_COLUMNS)
        for r in results:
            writer.writerow(
                [r.case_id, r.collection, r.size_bin_eval, cell(r.dice), cell(r.hd95), r.status]
            )


def write_summary(summary: dict, out: Path) -> None:
    """JSON with sorted keys and rounded numbers, so two runs give identical files."""
    out.write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    """Write per_case.csv and summary.json to --out; return 1 if predictions are missing."""
    parser = argparse.ArgumentParser(description="Evaluate predicted segmentation masks.")
    parser.add_argument("--pred", type=Path, required=True, help="directory of predicted masks")
    parser.add_argument("--gt", type=Path, required=True, help="directory of ground-truth masks")
    parser.add_argument("--split", type=Path, required=True, help="frozen_split_official.csv")
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    parser.add_argument("--splits", type=Path, help="nnU-Net splits_final.json; needs --fold")
    parser.add_argument("--fold", type=int, help="score only this fold's validation cases")
    args = parser.parse_args(argv)
    if (args.splits is None) != (args.fold is None):
        parser.error("--splits and --fold go together")

    only = read_fold_cases(args.splits, args.fold) if args.splits else None
    results = evaluate(args.pred, args.gt, read_case_info(args.split), only)
    summary = summarize(results)
    args.out.mkdir(parents=True, exist_ok=True)
    write_per_case(results, args.out / "per_case.csv")
    write_summary(summary, args.out / "summary.json")

    missing = [r.case_id for r in results if r.status == "missing"]
    print(f"{len(results)} cases -> {args.out}")
    if missing:
        print(f"{len(missing)} missing predictions: {', '.join(missing)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
