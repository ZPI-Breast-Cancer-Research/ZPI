# DICOM study → NIfTI model input

Converts one DICOM study into the input format of the segmentation model:

```
DICOM study → series → phases → roles (pre, post1, post2) → {case}_000N.nii.gz + manifest
```

`conversion.py` is pure Python with no Django imports and no Orthanc access. Its input is a
directory with the files of one study; fetching a study from Orthanc is #20.

## Run

From the repo root:

```bash
python -m workers.segmentation.conversion \
  --study data/dicom/ISPY1_1013 --case-id ISPY1_1013 --out data/nifti/ISPY1_1013
```

The exit code is 0 for status `ok` and 1 otherwise. A manifest is always written, NIfTI files only
for `ok`, so a study is never converted partially.

## Status

| Status | Meaning |
|---|---|
| `ok` | one dynamic acquisition with at least 3 phases, equal slice spacing |
| `niekompletne` | no dynamic acquisition with 3 phases; the manifest lists the missing roles |
| `niejednoznaczne` | more than one dynamic acquisition; the manifest lists the candidates, nothing is guessed |
| `zla_geometria` | the selected phases have uneven slice spacing or differ in size or pixel spacing |

## How roles are assigned

Series names differ between scanners (`ax dyn pre`, `Ph1/ax 3d dyn`, `Dynamic-3dfgre`), so they are
not used.

1. Keep series that are `MR`, `ORIGINAL` and `MRAcquisitionType = 3D`. This drops reports, SEG
   objects, derived maps (`SER`, `PE1`, subtractions), locators and diffusion.
2. Split each series into phases by slice position, then by `AcquisitionTime`. A series holds one
   phase (Duke) or all of them (ISPY1, where `Dynamic-3dfgre` has 3 × 60 files).
3. Group phases with the same geometry. Each group is one acquisition.
4. Sort the phases of the acquisition by time: the first three are `pre`, `post1`, `post2`
   (`workers/segmentation/channels.py`). Later phases are ignored.

## Voxels and affine

The model must get the same array it was trained on, so the voxel layout follows MAMA-MIA: slices
sorted along the normal, array axis 0 towards negative RAS, axes 1 and 2 towards positive RAS.

The affine comes from the DICOM geometry and **deliberately differs from MAMA-MIA**. In the checked
MAMA-MIA files the slice axis of the affine is mirrored relative to DICOM, while the array is not:

| Case | Slice `k=0` according to DICOM | According to MAMA-MIA | This module | MAMA-MIA |
|---|---|---|---|---|
| DUKE_009 | `z = -93.1` | `z = +77.4` | `LAS` | `LAI` |
| ISPY1_1013 | `x = +32.6` | `x = +150.6` | `PSR` | `PSL` |

nnU-Net trains on the array, so this does not change the model input. A true affine is needed to
map a predicted mask back to the patient.

## Manifest

`{case}_manifest.json` holds the status, the code version (`GIT_COMMIT` or `git rev-parse HEAD`),
for each role the series, acquisition time, shape and affine, the missing roles or candidates, and
the reason each series was rejected. It has no conversion timestamp: two runs give identical NIfTI
and manifest bytes.

## Checked on

| Study | Result |
|---|---|
| Duke `Breast_MRI_009` (TCIA) vs `DUKE_009` | voxels identical in all 3 channels |
| ISPY1 `ISPY1_1013`, first study (TCIA) | voxels identical in all 3 channels |
| Duke `Breast_MRI_001` (TCIA) | `ok`; no local MAMA-MIA NIfTI to compare with |

## Known limits

- The rules come from these three studies. NACT, ISPY2 and hospital data are not checked yet.
- The first phase of an acquisition is assumed to be pre-contrast.
- A missing file in a Duke-style series changes its geometry, so the phase drops out of the group
  and the result is `niekompletne`, not `zla_geometria`.
- `AcquisitionTime` is compared as text, so a study running past midnight would be misordered.
- `RescaleSlope` / `RescaleIntercept` handling has not been run on real data: the checked series do
  not have these tags.
- The synthetic Plastimatch DICOMs (`CT`, `DERIVED`) do not pass the series filter.
