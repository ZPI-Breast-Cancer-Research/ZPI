import csv
import json
import math
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from workers.segmentation.channels import CHANNELS
from workers.training.segmentation import build_nnunet_dataset as nnunet
from workers.training.segmentation import evaluate as ev
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


def make_manifest(root: Path, splits: dict[str, str]) -> Path:
    for case_id in splits:
        make_case(root, case_id)
    records, _ = build_manifest(root, splits)
    manifest = root / "manifest.csv"
    write_manifest(records, manifest)
    return manifest


def test_build_nnunet_dataset_layout(tmp_path):
    source = tmp_path / "mamamia"
    manifest = make_manifest(source, {"A_1": "train", "B_2": "test"})

    dataset_dir, counts = nnunet.build_nnunet_dataset(source, manifest, tmp_path / "raw")

    assert dataset_dir == tmp_path / "raw" / "Dataset501_DCE3"
    assert counts == {"train": 1, "test": 1}
    assert sorted(p.name for p in (dataset_dir / "imagesTr").iterdir()) == [
        "A_1_0000.nii.gz",
        "A_1_0001.nii.gz",
        "A_1_0002.nii.gz",
    ]
    assert [p.name for p in (dataset_dir / "labelsTr").iterdir()] == ["A_1.nii.gz"]
    assert len(list((dataset_dir / "imagesTs").iterdir())) == 3
    assert [p.name for p in (dataset_dir / "labelsTs").iterdir()] == ["B_2.nii.gz"]
    link = dataset_dir / "imagesTr" / "A_1_0001.nii.gz"
    assert link.resolve() == (source / "images" / "A_1" / "A_1_0001.nii.gz").resolve()


def test_dataset_json(tmp_path):
    source = tmp_path / "mamamia"
    manifest = make_manifest(source, {"A_1": "train", "B_2": "train", "C_3": "test"})

    dataset_dir, _ = nnunet.build_nnunet_dataset(source, manifest, tmp_path / "raw")

    assert json.loads((dataset_dir / "dataset.json").read_text(encoding="utf-8")) == {
        "channel_names": {"0": "pre", "1": "post1", "2": "post2"},
        "labels": {"background": 0, "tumor": 1},
        "numTraining": 2,
        "file_ending": ".nii.gz",
    }


def test_relative_source_root_gives_working_links(tmp_path, monkeypatch):
    manifest = make_manifest(tmp_path / "mamamia", {"A_1": "train"})
    monkeypatch.chdir(tmp_path)

    dataset_dir, _ = nnunet.build_nnunet_dataset(Path("mamamia"), manifest, Path("raw"))

    links = list((dataset_dir / "imagesTr").iterdir())
    assert links and all(link.exists() for link in links)


def test_copy_creates_regular_files(tmp_path):
    source = tmp_path / "mamamia"
    manifest = make_manifest(source, {"A_1": "train"})

    dataset_dir, _ = nnunet.build_nnunet_dataset(source, manifest, tmp_path / "raw", copy=True)

    files = list((dataset_dir / "imagesTr").iterdir())
    assert files and not any(f.is_symlink() for f in files)


def test_existing_dataset_needs_overwrite(tmp_path):
    source = tmp_path / "mamamia"
    manifest = make_manifest(source, {"A_1": "train"})
    args = ["--root", str(source), "--manifest", str(manifest), "--out", str(tmp_path / "raw")]
    assert nnunet.main(args) == 0
    stale = tmp_path / "raw" / "Dataset501_DCE3" / "imagesTr" / "OLD_0000.nii.gz"
    stale.touch()

    assert nnunet.main(args) == 1
    assert stale.exists()

    assert nnunet.main([*args, "--overwrite"]) == 0
    assert not stale.exists()
    assert source.joinpath("images", "A_1", "A_1_0000.nii.gz").exists()


def test_unknown_split_is_rejected_before_writing(tmp_path):
    source = tmp_path / "mamamia"
    manifest = make_manifest(source, {"A_1": "train"})
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(",train,", ",tset,"))

    with pytest.raises(ValueError, match="tset"):
        nnunet.build_nnunet_dataset(source, manifest, tmp_path / "raw")
    assert not (tmp_path / "raw").exists()


# --- evaluate.py (SEG-9) ---

SPLIT_HEADER = "patient_id,collection,split,tumor_ml,size_bin_eval\n"


def _cube(offset=0, shape=(32, 32, 32)):
    mask = np.zeros(shape, dtype=np.uint8)
    mask[10 + offset : 20 + offset, 10:20, 10:20] = 1
    return mask


def _save(path, mask, affine=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nib.Nifti1Image(mask, np.eye(4) if affine is None else affine), path)


def _split(tmp_path, rows):
    path = tmp_path / "split.csv"
    path.write_text(SPLIT_HEADER + "".join(f"{r}\n" for r in rows), encoding="utf-8")
    return path


def _cli(tmp_path, split, out="out"):
    return ["--pred", str(tmp_path / "pred"), "--gt", str(tmp_path / "gt"),
            "--split", str(split), "--out", str(tmp_path / out)]  # fmt: skip


def test_identical_masks_give_dice_1_and_hd95_0():
    mask = _cube().astype(bool)
    assert ev.dice(mask, mask) == 1.0
    assert ev.hd95(mask, mask, (1.0, 1.0, 1.0)) == 0.0


def test_hd95_is_in_mm():
    pred, gt = _cube(2).astype(bool), _cube().astype(bool)
    assert ev.dice(pred, gt) == pytest.approx(0.8)
    assert ev.hd95(pred, gt, (1.0, 1.0, 1.0)) == pytest.approx(2.0)
    assert ev.hd95(pred, gt, (2.0, 1.0, 1.0)) == pytest.approx(4.0)


def test_mask_touching_the_volume_border_has_a_surface():
    mask = np.zeros((16, 16, 16), dtype=bool)
    mask[:5, :5, :5] = True
    assert ev.hd95(mask, np.roll(mask, 1, axis=0), (1.0, 1.0, 1.0)) == pytest.approx(1.0)


def test_evaluation_writes_per_case_metrics(tmp_path):
    _save(tmp_path / "gt" / "DUKE_001.nii.gz", _cube())
    _save(tmp_path / "pred" / "DUKE_001.nii.gz", _cube(2))
    split = _split(tmp_path, ["DUKE_001,DUKE,train,1.0,<1 ml"])

    assert ev.main(_cli(tmp_path, split)) == 0

    rows = (tmp_path / "out" / "per_case.csv").read_text(encoding="utf-8").splitlines()
    assert rows == [",".join(ev.PER_CASE_COLUMNS), "DUKE_001,DUKE,<1 ml,0.8000,2.0000,ok"]


def test_summary_has_means_and_counts_per_group(tmp_path):
    _save(tmp_path / "gt" / "DUKE_001.nii.gz", _cube())
    _save(tmp_path / "pred" / "DUKE_001.nii.gz", _cube())
    _save(tmp_path / "gt" / "DUKE_002.nii.gz", _cube())
    _save(tmp_path / "pred" / "DUKE_002.nii.gz", _cube(2))
    _save(tmp_path / "gt" / "NACT_001.nii.gz", _cube())
    _save(tmp_path / "pred" / "NACT_001.nii.gz", _cube(2))
    cases = ev.read_case_info(
        _split(
            tmp_path,
            [
                "DUKE_001,DUKE,train,1.0,<1 ml",
                "DUKE_002,DUKE,train,9.0,5–20 ml",
                "NACT_001,NACT,train,9.0,5–20 ml",
            ],
        )
    )

    summary = ev.summarize(ev.evaluate(tmp_path / "pred", tmp_path / "gt", cases))

    assert summary["overall"]["n"] == 3
    assert summary["overall"]["dice_mean"] == pytest.approx((1.0 + 0.8 + 0.8) / 3, abs=1e-4)
    assert summary["collection"]["DUKE"] == {
        "n": 2,
        "n_missing": 0,
        "n_hd95": 2,
        "dice_mean": 0.9,
        "hd95_mean": 1.0,
    }
    assert summary["collection"]["NACT"]["n"] == 1
    assert summary["size_bin_eval"]["5–20 ml"]["dice_mean"] == 0.8
    assert summary["size_bin_eval"]["<1 ml"]["n"] == 1


def test_different_geometry_stops_with_the_case_name(tmp_path):
    shifted = np.eye(4)
    shifted[0, 3] = 5.0
    _save(tmp_path / "gt" / "DUKE_001.nii.gz", _cube())
    _save(tmp_path / "pred" / "DUKE_001.nii.gz", _cube(), affine=shifted)
    cases = ev.read_case_info(_split(tmp_path, ["DUKE_001,DUKE,train,1.0,<1 ml"]))

    with pytest.raises(ValueError, match="DUKE_001"):
        ev.evaluate(tmp_path / "pred", tmp_path / "gt", cases)


def test_different_shape_stops_with_the_case_name(tmp_path):
    _save(tmp_path / "gt" / "DUKE_001.nii.gz", _cube())
    _save(tmp_path / "pred" / "DUKE_001.nii.gz", _cube(shape=(32, 32, 30)))
    cases = ev.read_case_info(_split(tmp_path, ["DUKE_001,DUKE,train,1.0,<1 ml"]))

    with pytest.raises(ValueError, match="DUKE_001"):
        ev.evaluate(tmp_path / "pred", tmp_path / "gt", cases)


@pytest.mark.parametrize(
    "pred, gt, expected",
    [
        (
            np.zeros((32, 32, 32), np.uint8),
            np.zeros((32, 32, 32), np.uint8),
            (1.0, 0.0, "both_empty"),
        ),
        (np.zeros((32, 32, 32), np.uint8), _cube(), (0.0, math.nan, "empty_pred")),
        (_cube(), np.zeros((32, 32, 32), np.uint8), (0.0, math.nan, "empty_gt")),
    ],
    ids=["both-empty", "empty-prediction", "empty-ground-truth"],
)
def test_empty_masks_follow_the_rule_and_are_counted(tmp_path, pred, gt, expected):
    _save(tmp_path / "gt" / "DUKE_001.nii.gz", gt)
    _save(tmp_path / "pred" / "DUKE_001.nii.gz", pred)
    cases = ev.read_case_info(_split(tmp_path, ["DUKE_001,DUKE,train,1.0,<1 ml"]))

    results = ev.evaluate(tmp_path / "pred", tmp_path / "gt", cases)
    summary = ev.summarize(results)

    (result,) = results
    dice, hd95, status = expected
    assert (result.dice, result.status) == (dice, status)
    assert result.hd95 == hd95 or (math.isnan(result.hd95) and math.isnan(hd95))
    assert summary["overall"]["n"] == 1
    assert summary["overall"]["dice_mean"] == dice


def test_case_without_a_prediction_is_reported_missing(tmp_path, capsys):
    _save(tmp_path / "gt" / "DUKE_001.nii.gz", _cube())
    _save(tmp_path / "gt" / "DUKE_002.nii.gz", _cube())
    _save(tmp_path / "pred" / "DUKE_001.nii.gz", _cube())
    split = _split(tmp_path, ["DUKE_001,DUKE,train,1.0,<1 ml", "DUKE_002,DUKE,train,1.0,<1 ml"])

    code = ev.main(_cli(tmp_path, split))

    summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
    assert code == 1
    assert summary["missing"] == ["DUKE_002"]
    assert (summary["overall"]["n"], summary["overall"]["n_missing"]) == (2, 1)
    assert summary["overall"]["dice_mean"] == 1.0
    assert "DUKE_002" in capsys.readouterr().out


def test_two_runs_give_identical_reports(tmp_path):
    _save(tmp_path / "gt" / "DUKE_001.nii.gz", _cube())
    _save(tmp_path / "pred" / "DUKE_001.nii.gz", _cube(2))
    _save(tmp_path / "gt" / "NACT_001.nii.gz", _cube())
    split = _split(tmp_path, ["DUKE_001,DUKE,train,1.0,<1 ml", "NACT_001,NACT,train,9.0,5–20 ml"])
    ev.main(_cli(tmp_path, split, out="a"))
    ev.main(_cli(tmp_path, split, out="b"))

    for name in ("per_case.csv", "summary.json"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_hd95_does_not_depend_on_the_volume_around_the_masks():
    small = _cube().astype(bool)
    large = np.zeros((96, 96, 96), dtype=bool)
    large[:32, :32, :32] = small
    shifted = np.roll(large, 3, axis=1)
    assert ev.hd95(large, shifted, (1.0, 1.0, 1.0)) == ev.hd95(
        small, np.roll(small, 3, axis=1), (1.0, 1.0, 1.0)
    )


def test_fold_limits_the_evaluation_to_its_validation_cases(tmp_path):
    for case in ("DUKE_001", "DUKE_002"):
        _save(tmp_path / "gt" / f"{case}.nii.gz", _cube())
    _save(tmp_path / "pred" / "DUKE_002.nii.gz", _cube())
    split = _split(tmp_path, ["DUKE_001,DUKE,train,1.0,<1 ml", "DUKE_002,DUKE,train,1.0,<1 ml"])
    splits = tmp_path / "splits_final.json"
    splits.write_text(json.dumps([{"train": ["DUKE_001"], "val": ["DUKE_002"]}]), encoding="utf-8")

    code = ev.main([*_cli(tmp_path, split), "--splits", str(splits), "--fold", "0"])

    summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
    assert code == 0
    assert (summary["overall"]["n"], summary["missing"]) == (1, [])
