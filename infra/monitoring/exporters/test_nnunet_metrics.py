import os
from datetime import datetime
from pathlib import Path

from nnunet_metrics import main, newest_log, parse_log, render, run_labels

LOG = """\
2026-11-04 23:44:08.232936: Unable to plot network architecture: nnUNet_compile is enabled!
2026-11-04 23:44:08.266630:
2026-11-04 23:44:08.267104: Epoch 0
2026-11-04 23:44:08.267335: Current learning rate: 0.01
some compiler warning without a timestamp
2026-11-04 23:46:54.577734: train_loss -0.2656
2026-11-04 23:46:54.577849: val_loss -0.2882
2026-11-04 23:46:54.577902: Pseudo dice [np.float32(0.3697)]
2026-11-04 23:46:54.577962: Epoch time: 166.32 s
2026-11-04 23:46:54.578010: Yayy! New best EMA pseudo Dice: 0.36970001459121704
2026-11-04 23:46:55.473443: Epoch 1
2026-11-04 23:46:55.473517: Current learning rate: 0.00818
"""


def test_parse_log_returns_last_finished_epoch():
    progress = parse_log(LOG)

    assert progress.epoch == 0  # epoch 1 has started, but has not finished
    assert progress.train_loss == -0.2656
    assert progress.val_loss == -0.2882
    assert progress.pseudo_dice == 0.3697
    assert progress.epoch_seconds == 166.32
    assert progress.finished_at == datetime(2026, 11, 4, 23, 46, 54, 577962).timestamp()


def test_parse_log_handles_trailing_spaces_of_real_logs():
    log = "".join(f"{line} \n" for line in LOG.splitlines())

    assert parse_log(log) == parse_log(LOG)
    assert parse_log(log).epoch == 0


def test_parse_log_without_a_finished_epoch():
    assert parse_log("2026-11-04 23:44:08.267104: Epoch 0\n") is None
    assert parse_log("") is None


def test_parse_log_averages_pseudo_dice_of_many_classes():
    log = (
        "2026-11-04 23:44:08.000000: Epoch 3\n"
        "2026-11-04 23:44:09.000000: Pseudo dice [np.float32(0.2), np.float32(0.4)]\n"
        "2026-11-04 23:44:10.000000: Epoch time: 10.0 s\n"
    )

    assert round(parse_log(log).pseudo_dice, 6) == 0.3


def test_render_without_progress_reports_only_running():
    assert render(None, {}, running=False) == "nnunet_running 0\n"


def test_render_labels_every_metric():
    labels = {"dataset": "Dataset501_DCE3", "trainer": "nnUNetTrainer_5epochs", "fold": "0"}

    text = render(parse_log(LOG), labels, running=True)

    assert "nnunet_running 1\n" in text
    assert (
        'nnunet_epoch{dataset="Dataset501_DCE3",fold="0",trainer="nnUNetTrainer_5epochs"} 0\n'
        in text
    )


def make_log(results: Path, trainer: str, fold: str, mtime: float) -> Path:
    fold_dir = results / "Dataset501_DCE3" / f"{trainer}__nnUNetPlans__3d_fullres" / f"fold_{fold}"
    fold_dir.mkdir(parents=True)
    log = fold_dir / "training_log_2026_11_4.txt"
    log.write_text(LOG, encoding="utf-8")
    os.utime(log, (mtime, mtime))
    return log


def test_newest_log_and_its_labels(tmp_path):
    make_log(tmp_path, "nnUNetTrainer_5epochs", "0", mtime=100)
    newest = make_log(tmp_path, "nnUNetTrainer_100epochs", "1", mtime=200)

    assert newest_log(tmp_path) == newest
    assert run_labels(newest) == {
        "dataset": "Dataset501_DCE3",
        "trainer": "nnUNetTrainer_100epochs",
        "fold": "1",
    }


def test_main_writes_a_file_for_empty_results(tmp_path):
    out = tmp_path / "nnunet.prom"

    assert main(["--results", str(tmp_path), "--out", str(out), "--once"]) == 0
    assert out.read_text().startswith("nnunet_running ")
    assert not out.with_suffix(".tmp").exists()
