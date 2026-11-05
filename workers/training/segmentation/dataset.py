import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from workers.segmentation.channels import CHANNELS

# File suffixes used by MAMA-MIA for each role (a fact about the source, not the model).
MAMAMIA_PHASES = {"pre": "0000", "post1": "0001", "post2": "0002"}

IMAGES_DIR = "images"
LABELS_DIR = "segmentations"

MANIFEST_COLUMNS = ("case_id", "split", *CHANNELS, "label")


@dataclass(frozen=True)
class CaseRecord:
    case_id: str
    split: str
    images: dict[str, str]  # role -> path relative to root
    label: str  # path relative to root


@dataclass(frozen=True)
class Problem:
    case_id: str
    reason: str


def read_train_test_splits(csv_path: Path) -> dict[str, str]:
    """case_id -> "train" | "test" from frozen_split_official.csv."""
    cases: dict[str, str] = {}

    with csv_path.open(encoding="utf-8", newline="") as splits_file:
        for row in csv.DictReader(splits_file):
            patient_id = row["patient_id"]
            if patient_id in cases:
                raise ValueError(f"Duplicate patient_id {patient_id!r} in {csv_path}")
            cases[patient_id] = row["split"]

    return cases


def discover_mamamia(root: Path) -> list[str]:
    """Sorted case ids: subdirectories of root/images."""
    return sorted(case.name for case in (root / IMAGES_DIR).iterdir() if case.is_dir())


def build_record(root: Path, case_id: str, split: str) -> CaseRecord | list[Problem]:
    """Record if all phases and the label exist, otherwise every problem found."""
    problems: list[Problem] = []
    images: dict[str, str] = {}

    for role in CHANNELS:
        rel = Path(IMAGES_DIR) / case_id / f"{case_id}_{MAMAMIA_PHASES[role]}.nii.gz"
        if (root / rel).exists():
            images[role] = rel.as_posix()
        else:
            problems.append(Problem(case_id, f"missing phase {role}"))

    rel_label = Path(LABELS_DIR) / f"{case_id}.nii.gz"
    if not (root / rel_label).exists():
        problems.append(Problem(case_id, "missing label"))

    if problems:
        return problems
    return CaseRecord(case_id, split, images, rel_label.as_posix())


def build_manifest(root: Path, splits: dict[str, str]) -> tuple[list[CaseRecord], list[Problem]]:
    """Records sorted by case_id plus problems (missing files, cases not in split)."""
    records: list[CaseRecord] = []
    problems: list[Problem] = []

    for case_id in discover_mamamia(root):
        if case_id not in splits:
            problems.append(Problem(case_id, "not in split"))
            continue
        result = build_record(root, case_id, splits[case_id])
        if isinstance(result, CaseRecord):
            records.append(result)
        else:
            problems.extend(result)

    return records, problems


def write_manifest(records: list[CaseRecord], out: Path) -> None:
    """CSV with MANIFEST_COLUMNS, one row per record."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as manifest_file:
        writer = csv.DictWriter(manifest_file, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "case_id": record.case_id,
                    "split": record.split,
                    **record.images,
                    "label": record.label,
                }
            )


def main(argv: list[str] | None = None) -> int:
    """--root, --split, --out; print a summary; return 1 if there were problems."""
    parser = argparse.ArgumentParser(description="Build a MAMA-MIA manifest.")
    parser.add_argument(
        "--root", type=Path, required=True, help="MAMA-MIA directory with images/, segmentations/"
    )
    parser.add_argument("--split", type=Path, required=True, help="frozen_split_official.csv")
    parser.add_argument("--out", type=Path, required=True, help="output manifest CSV")
    args = parser.parse_args(argv)

    records, problems = build_manifest(args.root, read_train_test_splits(args.split))
    write_manifest(records, args.out)

    counts = Counter(record.split for record in records)
    summary = ", ".join(f"{split}: {n}" for split, n in sorted(counts.items()))
    print(f"{len(records)} records ({summary}) -> {args.out}")
    if problems:
        print(f"{len(problems)} problems:")
        for problem in problems:
            print(f"  {problem.case_id}: {problem.reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
