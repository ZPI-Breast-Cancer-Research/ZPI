# Segmentation training data (MAMA-MIA → nnU-Net)

Prepares the MAMA-MIA breast DCE-MRI dataset for nnU-Net v2 training:

```
MAMA-MIA + frozen split → dataset.py → manifest CSV → build_nnunet_dataset.py → $nnUNet_raw/Dataset501_DCE3
```

Pure Python with no Django imports. `dataset.py` knows the MAMA-MIA layout,
`build_nnunet_dataset.py` knows the nnU-Net layout; the manifest between them describes cases by
role (`pre`, `post1`, `post2`), so either side can change without touching the other.

## Channels

| Role | nnU-Net suffix | MAMA-MIA file |
|---|---|---|
| `pre` | `_0000` | `<case>_0000.nii.gz` (pre-contrast) |
| `post1` | `_0001` | `<case>_0001.nii.gz` (first post-contrast phase) |
| `post2` | `_0002` | `<case>_0002.nii.gz` (second post-contrast phase) |

The order is defined once in `workers/segmentation/channels.py` and shared with inference.
**Changing it invalidates every trained model.** MAMA-MIA phases beyond `_0002` are ignored; cases
missing any of the three phases or the expert mask are reported and left out.

## Data

- `--root`: MAMA-MIA directory with `images/<case>/<case>_000N.nii.gz` and
  `segmentations/<case>.nii.gz`. Manifest paths are relative to it, so use the same `--root` for
  both scripts (e.g. a symlink `data/mamamia`).
- Split: `data/splits/frozen_split_official.csv` (official MAMA-MIA split). Train cases go to
  `imagesTr` / `labelsTr`, test cases only to `imagesTs` / `labelsTs`; nnU-Net never trains on them.

## Environment

nnU-Net finds datasets through three variables. Locally (outside Docker) point them at `data/`:

```bash
export nnUNet_raw="$PWD/data/nnunet/raw"
export nnUNet_preprocessed="$PWD/data/nnunet/preprocessed"
export nnUNet_results="$PWD/data/nnunet/results"
```

In containers they come from `.env` (`/data/nnunet/...`).

## Run

From the repo root:

```bash
python -m workers.training.segmentation.dataset \
  --root data/mamamia \
  --split data/splits/frozen_split_official.csv \
  --out data/manifests/mamamia.csv

python -m workers.training.segmentation.build_nnunet_dataset \
  --root data/mamamia \
  --manifest data/manifests/mamamia.csv

nnUNetv2_plan_and_preprocess -d 501 -c 3d_fullres --verify_dataset_integrity
```

`dataset.py` exits with code 1 and lists the problems (missing phase, missing mask, case not in
the split) if any case was left out.

`build_nnunet_dataset.py` options:

- `--overwrite`: delete and rebuild an existing `Dataset501_DCE3` (without it the script refuses).
  Rerun `nnUNetv2_plan_and_preprocess` afterwards.
- `--copy`: copy files instead of symlinking. Symlinks point to absolute paths on the host, so use
  `--copy` when the dataset is read inside a container or on another machine.
- `--out`: nnU-Net raw directory (default: `$nnUNet_raw`).

## Dataset IDs

nnU-Net identifies datasets by number. Pick a new ID for any change of channels or data source.

| ID | Directory | Content |
|---|---|---|
| 501 | `Dataset501_DCE3` | MAMA-MIA, channels `pre` / `post1` / `post2` |

## Tests

```bash
pytest workers/segmentation workers/training/segmentation
```
