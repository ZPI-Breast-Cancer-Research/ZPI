import argparse
import csv
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

from workers.segmentation.channels import CHANNELS, channel_names, channel_suffix

DATASET_ID = 501
DATASET_NAME = "DCE3"
DATASET_DIRNAME = f"Dataset{DATASET_ID:03d}_{DATASET_NAME}"
LABELS = {"background": 0, "tumor": 1}
FILE_ENDING = ".nii.gz"

# split -> (images dir, labels dir)
SPLIT_DIRS = {"train": ("imagesTr", "labelsTr"), "test": ("imagesTs", "labelsTs")}


class DatasetExistsError(Exception):
    pass


def read_manifest(manifest: Path) -> list[dict[str, str]]:
    with manifest.open(encoding="utf-8", newline="") as manifest_file:
        rows = list(csv.DictReader(manifest_file))

    for row in rows:
        if row["split"] not in SPLIT_DIRS:
            raise ValueError(f"Unknown split {row['split']!r} for case {row['case_id']}")
    return rows


def prepare_dataset_dir(nnunet_raw: Path, overwrite: bool) -> Path:
    dataset_dir = nnunet_raw / DATASET_DIRNAME
    if dataset_dir.exists():
        if not overwrite:
            raise DatasetExistsError(f"{dataset_dir} already exists, use --overwrite to rebuild it")
        shutil.rmtree(dataset_dir)

    for images_dir, labels_dir in SPLIT_DIRS.values():
        (dataset_dir / images_dir).mkdir(parents=True)
        (dataset_dir / labels_dir).mkdir()
    
    return dataset_dir


def place_file(source: Path, target: Path, copy: bool) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Source file missing: {source}")
    if copy:
        shutil.copy2(source, target)
    else:
        # Absolute target: a relative one would be resolved against the link's own directory.
        target.symlink_to(source.resolve())


def place_case(source_root: Path, row: dict[str, str], dataset_dir: Path, copy: bool) -> None:
    case_id = row["case_id"]
    images_dir, labels_dir = (dataset_dir / name for name in SPLIT_DIRS[row["split"]])
    for role in CHANNELS:
        target = images_dir / f"{case_id}_{channel_suffix(role)}{FILE_ENDING}"
        place_file(source_root / row[role], target, copy)
    place_file(source_root / row["label"], labels_dir / f"{case_id}{FILE_ENDING}", copy)


def write_dataset_json(dataset_dir: Path, num_training: int) -> None:
    dataset = {
        "channel_names": channel_names(),
        "labels": LABELS,
        "numTraining": num_training,
        "file_ending": FILE_ENDING,
    }
    text = json.dumps(dataset, indent=2) + "\n"
    (dataset_dir / "dataset.json").write_text(text, encoding="utf-8")


def build_nnunet_dataset(
    source_root: Path,
    manifest: Path,
    nnunet_raw: Path,
    overwrite: bool = False,
    copy: bool = False,
) -> tuple[Path, Counter[str]]:
    rows = read_manifest(manifest)
    dataset_dir = prepare_dataset_dir(nnunet_raw, overwrite)
    for row in rows:
        place_case(source_root, row, dataset_dir, copy)
    counts = Counter(row["split"] for row in rows)
    write_dataset_json(dataset_dir, counts["train"])
    return dataset_dir, counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the nnU-Net raw dataset from a manifest.")
    parser.add_argument(
        "--root", type=Path, required=True, help="MAMA-MIA directory the manifest paths refer to"
    )
    parser.add_argument("--manifest", type=Path, required=True, help="manifest CSV from dataset.py")
    parser.add_argument(
        "--out",
        type=Path,
        default=os.environ.get("nnUNet_raw"),
        help="nnU-Net raw directory (default: $nnUNet_raw)",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help=f"delete and rebuild an existing {DATASET_DIRNAME}"
    )
    parser.add_argument("--copy", action="store_true", help="copy files instead of symlinking")
    args = parser.parse_args(argv)
    if args.out is None:
        parser.error("--out not given and nnUNet_raw is not set")

    try:
        dataset_dir, counts = build_nnunet_dataset(
            args.root, args.manifest, args.out, args.overwrite, args.copy
        )
    except (DatasetExistsError, FileNotFoundError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1

    print(f"{dataset_dir}: {counts['train']} train, {counts['test']} test")
    if args.overwrite:
        print(f"Rerun nnUNetv2_plan_and_preprocess -d {DATASET_ID} before training.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
