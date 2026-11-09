import argparse
import gzip
import json
import os
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from pathlib import Path
import nibabel as nib
import numpy as np
import nibabel as nib
import numpy as np
import pydicom
from highdicom.seg import (
    Segmentation,
    SegmentAlgorithmTypeValues,
    SegmentDescription,
    SegmentationTypeValues,
)
from highdicom.sr.coding import CodedConcept
from pydicom.errors import InvalidDicomError

from workers.segmentation.channels import CHANNELS, channel_suffix

LPS_TO_RAS = np.diag([-1.0, -1.0, 1.0, 1.0])
SLICE_GAP_TOLERANCE_MM = 0.01
# Sign of the main RAS direction of array axes 0, 1, 2 in the MAMA-MIA training data.
TRAINING_AXIS_SIGNS = (-1, 1, 1)


class GeometryError(Exception):
    pass


class Status(StrEnum):
    OK = "ok"
    INCOMPLETE = "niekompletne"
    AMBIGUOUS = "niejednoznaczne"
    BAD_GEOMETRY = "zla_geometria"


@dataclass(frozen=True)
class SeriesInfo:
    uid: str
    number: int | None
    description: str
    modality: str
    image_type: tuple[str, ...]
    acquisition_type: str
    files: tuple[Path, ...]


@dataclass(frozen=True)
class Phase:
    series_uid: str
    acquisition_time: str
    files: tuple[Path, ...]  # sorted by slice position along the normal
    geometry: tuple  # phases of one dynamic acquisition share it


@dataclass(frozen=True)
class RoleAssignment:
    status: Status
    roles: dict[str, Phase]
    missing: tuple[str, ...] = ()
    candidates: tuple[tuple[Phase, ...], ...] = ()


@dataclass(frozen=True)
class ConversionResult:
    status: Status
    nifti: dict[str, Path]
    manifest: dict


def read_series(study_dir: Path) -> list[SeriesInfo]:
    """Group the DICOM files under study_dir by SeriesInstanceUID, skipping other files."""
    series: dict[str, tuple[pydicom.Dataset, list[Path]]] = {}

    for path in sorted(study_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            header = pydicom.dcmread(path, stop_before_pixels=True)
        except InvalidDicomError:
            continue
        _, paths = series.setdefault(header.SeriesInstanceUID, (header, []))
        paths.append(path)

    result = []
    for uid, (header, paths) in series.items():
        number = getattr(header, "SeriesNumber", None)
        result.append(
            SeriesInfo(
                uid=uid,
                number=None if number is None else int(number),
                description=str(getattr(header, "SeriesDescription", "")),
                modality=str(getattr(header, "Modality", "")),
                image_type=tuple(str(v) for v in getattr(header, "ImageType", ())),
                acquisition_type=str(getattr(header, "MRAcquisitionType", "")),
                files=tuple(paths),
            )
        )
    return sorted(result, key=lambda s: (s.number is None, s.number or 0, s.uid))


def split_phases(series: SeriesInfo) -> list[Phase]:
    """Split a series into dynamic phases: one per acquisition at each slice position.

    A series holds one phase (Duke) or all of them (ISPY1), so phases come from the number of
    files per position, ordered by acquisition time.
    """
    headers = [pydicom.dcmread(path, stop_before_pixels=True) for path in series.files]
    normal = _slice_normal(series, headers)

    by_position: dict[float, list[tuple[str, int, Path]]] = {}
    for path, header in zip(series.files, headers, strict=True):
        if "ImagePositionPatient" not in header:
            raise GeometryError(f"Series {series.uid}: {path.name} has no ImagePositionPatient")
        position = round(float(np.dot(header.ImagePositionPatient, normal)), 3)
        time = str(getattr(header, "AcquisitionTime", ""))
        instance = int(getattr(header, "InstanceNumber", 0) or 0)
        by_position.setdefault(position, []).append((time, instance, path))

    counts = {len(items) for items in by_position.values()}
    if len(counts) != 1:
        raise GeometryError(
            f"Series {series.uid}: uneven number of files per slice position: {sorted(counts)}"
        )

    positions = sorted(by_position)
    for position in positions:
        by_position[position].sort()

    first = headers[0]
    geometry = (
        int(first.Rows),
        int(first.Columns),
        tuple(np.round(np.array(first.ImageOrientationPatient, dtype=float), 4).tolist()),
        tuple(np.round(np.array(first.PixelSpacing, dtype=float), 4).tolist()),
        tuple(positions),
    )

    phases = []
    for index in range(counts.pop()):
        slices = [by_position[position][index] for position in positions]
        phases.append(
            Phase(
                series_uid=series.uid,
                acquisition_time=min(time for time, _, _ in slices),
                files=tuple(path for _, _, path in slices),
                geometry=geometry,
            )
        )
    return phases


def _slice_normal(series: SeriesInfo, headers: list[pydicom.Dataset]) -> np.ndarray:
    if not headers or any("ImageOrientationPatient" not in header for header in headers):
        raise GeometryError(f"Series {series.uid}: missing ImageOrientationPatient")
    orientations = np.array([header.ImageOrientationPatient for header in headers], dtype=float)
    if not np.allclose(orientations, orientations[0], atol=1e-4):
        raise GeometryError(f"Series {series.uid}: slices have different orientations")
    return np.cross(orientations[0][:3], orientations[0][3:])


def load_volume(phase: Phase) -> tuple[np.ndarray, np.ndarray]:
    """Return the voxel array of a phase and its true RAS affine from the DICOM geometry.

    The array is laid out like the MAMA-MIA NIfTI files the model trains on: axis 0 points towards
    negative RAS, axes 1 and 2 towards positive RAS. The MAMA-MIA affines are not reproduced, as
    their slice axis is mirrored relative to DICOM.
    """
    slices = [pydicom.dcmread(path) for path in phase.files]
    first = slices[0]
    if len(slices) < 2:
        raise GeometryError(f"Series {phase.series_uid}: a volume needs at least 2 slices")
    if len({(s.Rows, s.Columns, tuple(map(float, s.PixelSpacing))) for s in slices}) != 1:
        raise GeometryError(f"Series {phase.series_uid}: slices differ in size or pixel spacing")

    orientation = np.array(first.ImageOrientationPatient, dtype=float)
    row_direction, column_direction = orientation[:3], orientation[3:]
    normal = np.cross(row_direction, column_direction)

    positions = np.array([np.dot(s.ImagePositionPatient, normal) for s in slices], dtype=float)
    gaps = np.diff(positions)
    if not np.allclose(gaps, gaps[0], atol=SLICE_GAP_TOLERANCE_MM) or gaps[0] <= 0:
        raise GeometryError(f"Series {phase.series_uid}: uneven slice spacing")

    # PixelSpacing is (between rows, between columns).
    row_spacing, column_spacing = map(float, first.PixelSpacing)
    affine = np.eye(4)
    affine[:3, 0] = row_direction * column_spacing
    affine[:3, 1] = column_direction * row_spacing
    affine[:3, 2] = normal * float(np.mean(gaps))
    affine[:3, 3] = np.array(first.ImagePositionPatient, dtype=float)
    affine = LPS_TO_RAS @ affine

    volume = np.stack([_pixels(s).T for s in slices], axis=-1)  # [column, row, slice]
    return _to_training_layout(volume, affine)


def _pixels(dataset: pydicom.Dataset) -> np.ndarray:
    pixels = dataset.pixel_array
    slope = float(getattr(dataset, "RescaleSlope", 1) or 1)
    intercept = float(getattr(dataset, "RescaleIntercept", 0) or 0)
    if slope == 1 and intercept == 0:
        return pixels
    return pixels * slope + intercept


def _to_training_layout(volume: np.ndarray, affine: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    affine = affine.copy()
    for axis, wanted_sign in enumerate(TRAINING_AXIS_SIGNS):
        direction = affine[:3, axis]
        if np.sign(direction[np.argmax(np.abs(direction))]) != wanted_sign:
            volume = np.flip(volume, axis)
            affine[:3, 3] += direction * (volume.shape[axis] - 1)
            affine[:3, axis] = -direction
    return volume, affine


def write_nifti(volume: np.ndarray, affine: np.ndarray, path: Path) -> None:
    """Write a .nii.gz with identical bytes on every run (mtime=0 in the gzip header)."""
    image = nib.Nifti1Image(volume, affine)
    image.set_sform(affine, code=1)
    image.set_qform(affine, code=1)
    image.header.set_xyzt_units("mm")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(image.to_bytes(), compresslevel=1, mtime=0))


def is_dynamic_candidate(series: SeriesInfo) -> bool:
    """Acquired 3D MR images only.

    Drops reports and SEG objects (modality), derived maps such as subtractions (image type), and
    2D series such as diffusion and locators, which can also repeat at each slice position.
    """
    return (
        series.modality == "MR"
        and series.image_type[:1] == ("ORIGINAL",)
        and series.acquisition_type == "3D"
    )


def assign_roles(phases: list[Phase]) -> RoleAssignment:
    """Assign phases to CHANNELS by acquisition order within one dynamic acquisition.

    Series names differ between scanners (`ax dyn pre`, `Ph1/ax 3d dyn`, `Dynamic-3dfgre`), so roles
    come from geometry and time: a dynamic acquisition is a group of phases with one geometry.
    """
    groups: dict[tuple, list[Phase]] = {}
    for phase in phases:
        groups.setdefault(phase.geometry, []).append(phase)
    ordered = [
        tuple(sorted(group, key=lambda p: (p.acquisition_time, p.series_uid)))
        for group in groups.values()
    ]

    dynamic = [group for group in ordered if len(group) >= len(CHANNELS)]
    if len(dynamic) > 1:
        return RoleAssignment(Status.AMBIGUOUS, {}, candidates=tuple(dynamic))
    if dynamic:
        return RoleAssignment(Status.OK, dict(zip(CHANNELS, dynamic[0], strict=False)))

    longest = max(ordered, key=len, default=())
    return RoleAssignment(
        Status.INCOMPLETE,
        dict(zip(CHANNELS, longest, strict=False)),
        missing=CHANNELS[len(longest) :],
    )


def convert_study(study_dir: Path, case_id: str, out_dir: Path) -> ConversionResult:
    """Convert one DICOM study to model input and a manifest; NIfTI only when the status is ok."""
    series = read_series(study_dir)
    series_by_uid = {s.uid: s for s in series}
    phases: list[Phase] = []
    rejected: dict[str, str] = {}
    for item in series:
        if not is_dynamic_candidate(item):
            rejected[item.uid] = (
                f"not an acquired 3D MR series: {item.description!r}, {item.modality}, "
                f"{item.image_type[:1]}, {item.acquisition_type!r}"
            )
            continue
        try:
            phases.extend(split_phases(item))
        except GeometryError as error:
            rejected[item.uid] = str(error)

    assignment = assign_roles(phases)
    status = assignment.status
    volumes: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    geometry_error = None
    if status is Status.OK:
        try:
            volumes = {role: load_volume(phase) for role, phase in assignment.roles.items()}
        except GeometryError as error:
            status = Status.BAD_GEOMETRY
            geometry_error = str(error)

    nifti: dict[str, Path] = {}
    for role, (volume, affine) in volumes.items():
        nifti[role] = out_dir / f"{case_id}_{channel_suffix(role)}.nii.gz"
        write_nifti(volume, affine, nifti[role])

    manifest = {
        "case_id": case_id,
        "status": str(status),
        "code_version": _code_version(),
        "channels": {
            role: _phase_entry(phase, series_by_uid, volumes.get(role))
            for role, phase in assignment.roles.items()
        },
        "missing_roles": list(assignment.missing),
        "candidates": [
            [_phase_entry(phase, series_by_uid) for phase in group]
            for group in assignment.candidates
        ],
        "geometry_error": geometry_error,
        "rejected_series": rejected,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{case_id}_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return ConversionResult(status, nifti, manifest)

def convert_nifti_to_dicom_seg(
    ref_dicom_dir: Path,
    mask_nifti_path: Path,
    output_seg_path: Path,
    segment_label: str = "Corrected Breast Lesion",
) -> Path:
    """Konwertuje poprawioną maskę NIfTI na format DICOM SEG przy użyciu geometrii

    oryginalnych serii DICOM pobranych z Orthanca.
    """
    dicom_paths = sorted(
        [p for p in ref_dicom_dir.rglob("*") if p.is_file()],
        key=lambda p: p.name,
    )
    dicom_files = []
    for p in dicom_paths:
        try:
            ds = pydicom.dcmread(p, stop_before_pixels=False)
            if hasattr(ds, "ImagePositionPatient") and hasattr(ds, "ImageOrientationPatient"):
                dicom_files.append(ds)
        except pydicom.errors.InvalidDicomError:
            continue

    if not dicom_files:
        raise GeometryError(f"Brak prawidłowych plików DICOM z geometrią w {ref_dicom_dir}")

    orientation = np.array(dicom_files[0].ImageOrientationPatient, dtype=float)
    normal = np.cross(orientation[:3], orientation[3:])
    dicom_files.sort(key=lambda f: float(np.dot(f.ImagePositionPatient, normal)))

    mask_img = nib.load(mask_nifti_path)
    mask_data = mask_img.get_fdata().astype(np.uint8)

    mask_binary = (mask_data > 0).astype(np.uint8)

    pixel_array = np.transpose(mask_binary, (2, 1, 0))

    if pixel_array.shape[0] != len(dicom_files):
        raise GeometryError(
            f"Liczba plasterków w masce NIfTI ({pixel_array.shape[0]}) "
            f"nie zgadza się z liczbą plików DICOM ({len(dicom_files)})"
        )

    segment_description = SegmentDescription(
        segment_number=1,
        segment_label=segment_label,
        property_category=CodedConcept(
            value="418363000",
            scheme_designator="SCT",
            meaning="Morphological Alteration",
        ),
        property_type=CodedConcept(
            value="108369006",
            scheme_designator="SCT",
            meaning="Tumor",
        ),
        algorithm_type=SegmentAlgorithmTypeValues.MANUAL,
    )

    seg = Segmentation(
        source_images=dicom_files,
        pixel_array=pixel_array,
        segmentation_type=SegmentationTypeValues.BINARY,
        segment_descriptions=[segment_description],
        series_instance_uid=pydicom.uid.generate_uid(),
        series_number=1000,
        sop_instance_uid=pydicom.uid.generate_uid(),
        instance_number=1,
        manufacturer="MARIA Project",
        manufacturer_model_name="NIfTI to DICOM SEG Converter",
        device_serial_number="1.0",
        software_versions="1.0",
    )

    output_seg_path.parent.mkdir(parents=True, exist_ok=True)
    seg.save_as(str(output_seg_path))
    return output_seg_path

def _phase_entry(
    phase: Phase,
    series_by_uid: dict[str, SeriesInfo],
    volume: tuple[np.ndarray, np.ndarray] | None = None,
) -> dict:
    series = series_by_uid[phase.series_uid]
    entry = {
        "series_instance_uid": phase.series_uid,
        "series_number": series.number,
        "series_description": series.description,
        "acquisition_time": phase.acquisition_time,
        "slices": len(phase.files),
    }
    if volume is not None:
        entry["shape"] = list(volume[0].shape)
        entry["affine"] = (np.round(volume[1], 6) + 0.0).tolist()  # + 0.0 turns -0.0 into 0.0
    return entry


def _code_version() -> str:
    if version := os.environ.get("GIT_COMMIT"):
        return version
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).parent,
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    """--study, --case-id, --out; print the result; return 1 unless the status is ok."""
    parser = argparse.ArgumentParser(description="Convert a DICOM study to NIfTI model input.")
    parser.add_argument("--study", type=Path, required=True, help="directory with one DICOM study")
    parser.add_argument("--case-id", required=True, help="prefix of the output files")
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    args = parser.parse_args(argv)

    result = convert_study(args.study, args.case_id, args.out)
    print(f"{args.case_id}: {result.status}")
    for role, path in result.nifti.items():
        print(f"  {role}: {path}")
    if result.manifest["missing_roles"]:
        print(f"  missing roles: {', '.join(result.manifest['missing_roles'])}")
    if result.manifest["geometry_error"]:
        print(f"  {result.manifest['geometry_error']}")
    return 0 if result.status is Status.OK else 1


if __name__ == "__main__":
    raise SystemExit(main())
