"""Write nnU-Net training progress as Prometheus metrics, for node_exporter's textfile collector.

Prometheus cannot read epochs from nnU-Net, so this script reads the training log. It runs next to
the training and never touches it. Standard library only, so it works in any Python.
"""

import argparse
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

TIMESTAMPED = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+): (.*)$")
FLOAT = r"[-+]?\d+\.\d+(?:[eE][-+]?\d+)?"


@dataclass(frozen=True)
class Progress:
    epoch: int
    train_loss: float | None
    val_loss: float | None
    pseudo_dice: float | None
    epoch_seconds: float
    finished_at: float


def parse_log(text: str) -> Progress | None:
    """Return the last finished epoch of a training log, or None if no epoch has finished."""
    current: dict[str, float | None] = {}
    epoch = None
    finished = None
    for line in text.splitlines():
        match = TIMESTAMPED.match(line)
        if not match:
            continue
        timestamp, message = match.groups()
        message = message.strip()  # nnU-Net ends log lines with a space

        if found := re.fullmatch(r"Epoch (\d+)", message):
            epoch = int(found.group(1))
            current = {}
        elif found := re.fullmatch(rf"train_loss ({FLOAT})", message):
            current["train_loss"] = float(found.group(1))
        elif found := re.fullmatch(rf"val_loss ({FLOAT})", message):
            current["val_loss"] = float(found.group(1))
        elif message.startswith("Pseudo dice"):
            # e.g. "Pseudo dice [np.float32(0.3697)]", one value per class.
            values = [float(value) for value in re.findall(FLOAT, message)]
            current["pseudo_dice"] = sum(values) / len(values) if values else None
        elif (found := re.fullmatch(rf"Epoch time: ({FLOAT}) s", message)) and epoch is not None:
            finished = Progress(
                epoch=epoch,
                train_loss=current.get("train_loss"),
                val_loss=current.get("val_loss"),
                pseudo_dice=current.get("pseudo_dice"),
                epoch_seconds=float(found.group(1)),
                finished_at=datetime.fromisoformat(timestamp).timestamp(),
            )
    return finished


def newest_log(results: Path) -> Path | None:
    logs = results.glob("*/*/fold_*/training_log_*.txt")
    return max(logs, key=lambda path: path.stat().st_mtime, default=None)


def run_labels(log: Path) -> dict[str, str]:
    """Read labels from `<dataset>/<trainer>__<plans>__<configuration>/fold_<n>/<log>`."""
    fold_dir = log.parent
    trainer = fold_dir.parent.name.split("__")[0]
    return {
        "dataset": fold_dir.parent.parent.name,
        "trainer": trainer,
        "fold": fold_dir.name.removeprefix("fold_"),
    }


def render(progress: Progress | None, labels: dict[str, str], running: bool) -> str:
    lines = [f"nnunet_running {int(running)}"]
    if progress is None:
        return "\n".join(lines) + "\n"

    tags = ",".join(f'{key}="{value}"' for key, value in sorted(labels.items()))
    values = {
        "nnunet_epoch": progress.epoch,
        "nnunet_train_loss": progress.train_loss,
        "nnunet_val_loss": progress.val_loss,
        "nnunet_pseudo_dice": progress.pseudo_dice,
        "nnunet_epoch_seconds": progress.epoch_seconds,
        "nnunet_last_epoch_timestamp_seconds": progress.finished_at,
    }
    lines += [f"{name}{{{tags}}} {value}" for name, value in values.items() if value is not None]
    return "\n".join(lines) + "\n"


def write_atomically(content: str, out: Path) -> None:
    # node_exporter must never read a half-written file.
    temporary = out.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, out)


def is_training_running() -> bool:
    return subprocess.run(["pgrep", "-f", "nnUNetv2_train"], capture_output=True).returncode == 0


def update(results: Path, out: Path) -> None:
    log = newest_log(results)
    if log is None:
        progress, labels = None, {}
    else:
        progress = parse_log(log.read_text(encoding="utf-8", errors="replace"))
        labels = run_labels(log)
    write_atomically(render(progress, labels, is_training_running()), out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=os.environ.get("nnUNet_results"))
    parser.add_argument("--out", type=Path, default=Path("infra/monitoring/textfile/nnunet.prom"))
    parser.add_argument("--interval", type=float, default=30, help="seconds between updates")
    parser.add_argument("--once", action="store_true", help="update once and exit")
    args = parser.parse_args(argv)
    if args.results is None:
        parser.error("--results not given and nnUNet_results is not set")

    while True:
        update(args.results, args.out)
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
