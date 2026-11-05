"""Select and download a balanced subset of MAMA-MIA training cases from Synapse."""

import argparse
import csv
import os
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .dataset import IMAGES_DIR, LABELS_DIR

IMAGES_FOLDER = "syn64871114"
EXPERT_LABELS_FOLDER = "syn64871175"  # sibling "automatic" masks must not be used for training
FILE_ENDING = ".nii.gz"
SEED = 42

# Collections with few cases are taken whole, the rest is split between the two large ones.
QUOTAS = {"DUKE": 125, "ISPY1": 104, "ISPY2": 124, "NACT": 47}

DEFAULT_SPLIT = Path("data/splits/frozen_split_official.csv")
DEFAULT_SELECTION = Path("data/splits/mamamia_train_400.csv")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def select_cases(
    rows: list[dict[str, str]],
    quotas: dict[str, int] = QUOTAS,
    keep: frozenset[str] = frozenset(),
    seed: int = SEED,
) -> list[dict[str, str]]:
    """Pick training cases per collection, keeping the size distribution of each collection."""
    selected = []
    for collection, quota in quotas.items():
        cases = [r for r in rows if r["split"] == "train" and r["collection"] == collection]
        if len(cases) < quota:
            raise ValueError(f"{collection}: {quota} cases requested, {len(cases)} available")
        selected.extend(_select_from_collection(cases, quota, keep, f"{seed}:{collection}"))
    return sorted(selected, key=lambda row: row["patient_id"])


def _select_from_collection(
    cases: list[dict[str, str]], quota: int, keep: frozenset[str], seed: str
) -> list[dict[str, str]]:
    ordered = sorted(cases, key=lambda row: row["patient_id"])
    random.Random(seed).shuffle(ordered)
    # Stable sort: cases to keep come first, the rest stays in random order.
    ordered.sort(key=lambda row: row["patient_id"] not in keep)

    bin_sizes = Counter(row["size_bin_eval"] for row in cases)
    targets = {name: quota * size / len(cases) for name, size in bin_sizes.items()}
    kept = [row for row in ordered if row["patient_id"] in keep][:quota]
    available = [row for row in ordered if row["patient_id"] not in keep]

    chosen = list(kept)
    counts = Counter(row["size_bin_eval"] for row in chosen)
    while len(chosen) < quota:
        open_bins = {row["size_bin_eval"] for row in available}
        name = max(sorted(open_bins), key=lambda b: targets[b] - counts[b])
        row = next(row for row in available if row["size_bin_eval"] == name)
        available.remove(row)
        chosen.append(row)
        counts[name] += 1
    return chosen


def write_selection(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def list_children(syn: Any, parent: str) -> dict[str, str]:
    return {child["name"]: child["id"] for child in syn.getChildren(parent)}


def _fetch(syn: Any, entity_id: str, directory: Path, name: str) -> bool:
    """Download one file unless it is already there; return True if it was downloaded."""
    target = directory / name
    if target.exists() and target.stat().st_size > 0:
        return False
    directory.mkdir(parents=True, exist_ok=True)
    syn.get(entity_id, downloadLocation=str(directory), ifcollision="overwrite.local")
    # Without download access syn.get returns metadata and raises nothing.
    if not target.exists():
        raise FileNotFoundError(f"{name} was not saved; check the Synapse login and data access")
    return True


def download_case(
    syn: Any, case_id: str, image_folders: dict[str, str], labels: dict[str, str], out: Path
) -> int:
    """Download the images and the expert mask of a case; return the number of new files."""
    label_name = f"{case_id}{FILE_ENDING}"
    if case_id not in image_folders:
        raise KeyError(f"no image folder on Synapse for {case_id}")
    if label_name not in labels:
        raise KeyError(f"no expert mask on Synapse for {case_id}")

    downloaded = 0
    images = list_children(syn, image_folders[case_id])
    names = sorted(name for name in images if name.endswith(FILE_ENDING))
    if not names:
        raise KeyError(f"no NIfTI files on Synapse for {case_id}")
    for name in names:
        downloaded += _fetch(syn, images[name], out / IMAGES_DIR / case_id, name)
    downloaded += _fetch(syn, labels[label_name], out / LABELS_DIR, label_name)
    return downloaded


def login() -> Any:
    try:
        import synapseclient
    except ImportError:
        sys.exit("synapseclient is not installed: pip install synapseclient")
    syn = synapseclient.Synapse()
    # Without the variable the client reads ~/.synapseConfig.
    syn.login(authToken=os.environ.get("SYNAPSE_AUTH_TOKEN"))
    return syn


def download_all(syn: Any, case_ids: list[str], out: Path) -> dict[str, str]:
    """Download every case; return failed cases with the reason, so a rerun can finish them."""
    image_folders = list_children(syn, IMAGES_FOLDER)
    labels = list_children(syn, EXPERT_LABELS_FOLDER)

    failed: dict[str, str] = {}
    for number, case_id in enumerate(case_ids, start=1):
        try:
            new_files = download_case(syn, case_id, image_folders, labels, out)
        except Exception as error:  # noqa: BLE001 - one bad case must not stop a long download
            failed[case_id] = f"{type(error).__name__}: {error}"
            print(f"[{number}/{len(case_ids)}] {case_id}: FAILED {error}", flush=True)
        else:
            print(f"[{number}/{len(case_ids)}] {case_id}: {new_files} new files", flush=True)
    return failed


def _select_command(args: argparse.Namespace) -> int:
    if args.selection.exists() and not args.overwrite:
        print(f"{args.selection} already exists, use --overwrite to replace it", file=sys.stderr)
        return 1
    keep: frozenset[str] = frozenset()
    if args.keep_from:
        keep = frozenset(p.name for p in (args.keep_from / IMAGES_DIR).iterdir() if p.is_dir())

    rows = select_cases(read_rows(args.split), keep=keep, seed=args.seed)
    write_selection(rows, args.selection)

    print(f"{len(rows)} cases -> {args.selection}")
    print(f"already on disk: {sum(row['patient_id'] in keep for row in rows)}")
    for key in ("collection", "size_bin_eval"):
        print(f"{key}: {dict(sorted(Counter(row[key] for row in rows).items()))}")
    return 0


def _download_command(args: argparse.Namespace) -> int:
    case_ids = [row["patient_id"] for row in read_rows(args.selection)]
    if args.limit is not None:
        case_ids = case_ids[: args.limit]

    failed = download_all(login(), case_ids, args.out)
    print(f"{len(case_ids) - len(failed)} of {len(case_ids)} cases ready in {args.out}")
    for case_id, reason in failed.items():
        print(f"  {case_id}: {reason}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    select = commands.add_parser("select", help="write the list of cases, no download")
    select.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    select.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    select.add_argument("--keep-from", type=Path, help="MAMA-MIA directory whose cases to keep")
    select.add_argument("--seed", type=int, default=SEED)
    select.add_argument("--overwrite", action="store_true", help="replace an existing list")
    select.set_defaults(run=_select_command)

    download = commands.add_parser("download", help="download the listed cases from Synapse")
    download.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    download.add_argument("--out", type=Path, required=True, help="MAMA-MIA directory to fill")
    download.add_argument("--limit", type=int, help="only the first N cases, for a quick check")
    download.set_defaults(run=_download_command)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
