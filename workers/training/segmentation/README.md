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

## Evaluation

Every model is scored by the same script, so results are comparable:

```bash
python -m workers.training.segmentation.evaluate \
  --pred  "$nnUNet_results/Dataset501_DCE3/<trainer>__nnUNetPlans__3d_fullres/fold_0/validation" \
  --gt    "$nnUNet_preprocessed/Dataset501_DCE3/gt_segmentations" \
  --split data/splits/frozen_split_official.csv \
  --splits "$nnUNet_preprocessed/Dataset501_DCE3/splits_final.json" --fold 0 \
  --out   "$nnUNet_results/Dataset501_DCE3/<trainer>__nnUNetPlans__3d_fullres/fold_0/evaluation"
```

`gt_segmentations` holds every training case; `--splits` with `--fold` keeps only that fold's
validation cases. Without them every ground-truth case is expected to have a prediction.

It writes `per_case.csv` (Dice, HD95 in mm, status per case) and `summary.json` (means overall,
per collection and per `size_bin_eval`, each with the number of cases). Cases are taken from the
ground truth; a case without a prediction is reported as `missing` and the script returns 1. A
prediction with a different shape or affine than its ground truth stops the run with the case name.

- HD95: 95th percentile of the distances between the two mask surfaces, both directions pooled.
- Empty masks: both empty → Dice 1, HD95 0. Only one empty → Dice 0, HD95 not defined; the case
  counts in `n` and in the Dice mean, but not in the HD95 mean (`n_hd95` says how many have one).

Models are selected on cross-validation. The frozen test set is used once, for the final evaluation
of the chosen model.

## Tests

```bash
pytest workers/segmentation workers/training/segmentation
```
