import csv
from pathlib import Path

import pytest

from workers.segmentation.channels import CHANNELS
from workers.training.segmentation.dataset import (
    MAMAMIA_PHASES,
    MANIFEST_COLUMNS,
    CaseRecord,
    Problem,
    build_manifest,
    build_record,
    discover_mamamia,
    main,
    read_train_test_splits,
    write_manifest,
)

ALL_PHASES = ("0000", "0001", "0002")


def make_case(root: Path, case_id: str, phases=ALL_PHASES, with_label: bool = True) -> None:
    case_dir = root / "images" / case_id
    case_dir.mkdir(parents=True)
    for phase in phases:
        (case_dir / f"{case_id}_{phase}.nii.gz").touch()
    if with_label:
        (root / "segmentations").mkdir(exist_ok=True)
        (root / "segmentations" / f"{case_id}.nii.gz").touch()


def write_splits(path: Path, rows: list[tuple[str, str]]) -> Path:
    lines = ["patient_id,split", *(f"{case_id},{split}" for case_id, split in rows)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_mamamia_phases_cover_every_channel():
    assert set(MAMAMIA_PHASES) == set(CHANNELS)


def test_read_train_test_splits(tmp_path):
    csv_path = write_splits(tmp_path / "split.csv", [("A_1", "train"), ("B_2", "test")])

    assert read_train_test_splits(csv_path) == {"A_1": "train", "B_2": "test"}


def test_read_train_test_splits_rejects_duplicates(tmp_path):
    csv_path = write_splits(tmp_path / "split.csv", [("A_1", "train"), ("A_1", "test")])

    with pytest.raises(ValueError, match="A_1"):
        read_train_test_splits(csv_path)


def test_discover_mamamia_returns_sorted_case_dirs_only(tmp_path):
    make_case(tmp_path, "B_2")
    make_case(tmp_path, "A_1")
    (tmp_path / "images" / "notes.txt").touch()

    assert discover_mamamia(tmp_path) == ["A_1", "B_2"]


def test_build_record_for_complete_case(tmp_path):
    make_case(tmp_path, "A_1", phases=(*ALL_PHASES, "0003"))

    record = build_record(tmp_path, "A_1", "train")

    assert record == CaseRecord(
        case_id="A_1",
        split="train",
        images={
            "pre": "images/A_1/A_1_0000.nii.gz",
            "post1": "images/A_1/A_1_0001.nii.gz",
            "post2": "images/A_1/A_1_0002.nii.gz",
        },
        label="segmentations/A_1.nii.gz",
    )


def test_build_record_reports_every_missing_file(tmp_path):
    make_case(tmp_path, "A_1", phases=("0000",), with_label=False)

    problems = build_record(tmp_path, "A_1", "train")

    assert problems == [
        Problem("A_1", "missing phase post1"),
        Problem("A_1", "missing phase post2"),
        Problem("A_1", "missing label"),
    ]


def test_build_manifest_splits_records_and_problems(tmp_path):
    make_case(tmp_path, "A_1")
    make_case(tmp_path, "B_2", phases=("0000",))
    make_case(tmp_path, "C_3")

    records, problems = build_manifest(tmp_path, {"A_1": "train", "B_2": "test"})

    assert [record.case_id for record in records] == ["A_1"]
    assert problems == [
        Problem("B_2", "missing phase post1"),
        Problem("B_2", "missing phase post2"),
        Problem("C_3", "not in split"),
    ]


def test_write_manifest_flattens_images_into_role_columns(tmp_path):
    make_case(tmp_path, "A_1")
    record = build_record(tmp_path, "A_1", "test")
    out = tmp_path / "manifests" / "manifest.csv"

    write_manifest([record], out)

    with out.open(encoding="utf-8", newline="") as manifest_file:
        reader = csv.DictReader(manifest_file)
        rows = list(reader)
    assert tuple(reader.fieldnames) == MANIFEST_COLUMNS
    assert rows == [
        {
            "case_id": "A_1",
            "split": "test",
            "pre": "images/A_1/A_1_0000.nii.gz",
            "post1": "images/A_1/A_1_0001.nii.gz",
            "post2": "images/A_1/A_1_0002.nii.gz",
            "label": "segmentations/A_1.nii.gz",
        }
    ]


def test_main_exit_code(tmp_path):
    make_case(tmp_path, "A_1")
    csv_path = write_splits(tmp_path / "split.csv", [("A_1", "train")])
    args = ["--root", str(tmp_path), "--split", str(csv_path), "--out", str(tmp_path / "m.csv")]

    assert main(args) == 0

    make_case(tmp_path, "B_2")
    assert main(args) == 1
