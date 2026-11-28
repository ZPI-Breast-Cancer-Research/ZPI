import logging
import os
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np
import pydicom
from common.errors import StorageError
from common.storage import BUCKET_MASKS, delete_object, upload_file
from config.celery import app
from django.db import DatabaseError, transaction
from mlops.models import ModelVersion
from patients.errors import OrthancUnavailable
from patients.models import Study
from patients.orthanc_client import OrthancClient
from pydicom.errors import InvalidDicomError
from segmentation.models import SegmentationResult, StatusChoices

from workers.segmentation.channels import CHANNELS
from workers.segmentation.conversion import (
    Algorithm,
    Status,
    convert_dicom_seg_to_nifti,
    convert_nifti_to_dicom_seg,
    convert_study,
)
from workers.segmentation.measurements import measure_file
from workers.segmentation.models.base import SegmentationError, SegmentationModel
from workers.segmentation.models.registry import get_segmentation_model

logger = logging.getLogger(__name__)

MODEL_DIR_ENV = "SEGMENTATION_MODEL_DIR"

# A radiologist verified these; no run replaces them.
VERIFIED = (StatusChoices.APPROVED, StatusChoices.CORRECTED)


class StudyGone(Exception):
    """The study was deleted while it was being segmented."""


# One model per worker process: loading nnU-Net weights takes longer than a prediction.
_models: dict[Path, SegmentationModel] = {}


def _model() -> SegmentationModel:
    model_dir = os.getenv(MODEL_DIR_ENV)
    if not model_dir:
        raise SegmentationError(f"Environment variable {MODEL_DIR_ENV} is not set")
    path = Path(model_dir)
    if path not in _models:
        _models[path] = get_segmentation_model(path)
    return _models[path]


def _model_version(model: SegmentationModel) -> ModelVersion | None:
    """The registered ModelVersion of the loaded weights, if the model is registered."""
    version = ModelVersion.objects.filter(
        module=ModelVersion.ModuleChoices.SEG, version=model.info.version
    ).first()
    if version is None:
        logger.warning("Model version %s is not registered in mlops", model.info.version)
    return version


def _series_ids(manifest: dict) -> list[str]:
    seen: list[str] = []
    for entry in (manifest.get("channels") or {}).values():
        uid = entry.get("series_instance_uid")
        if uid and uid not in seen:
            seen.append(uid)
    return seen


def _start(study_id: int) -> SegmentationResult | None:
    """Put the study's one result row in PROCESSING; None when the run must not happen.

    The row is created at import; a new run reuses it and replaces a result that is not verified,
    together with its mask file and its DICOM SEG.
    """
    with transaction.atomic():
        study = Study.objects.filter(pk=study_id).first()
        if study is None:
            logger.warning(
                "segmentation.run: study %s does not exist (deleted?), skipped", study_id
            )
            return None
        result, _ = SegmentationResult.objects.select_for_update().get_or_create(study=study)
        if result.status in VERIFIED:
            logger.info("segmentation.run: study %s is verified, skipped", study_id)
            return None
        previous_mask, previous_seg = result.generated_path, result.model_seg_series_uid

        result.status = StatusChoices.PROCESSING
        result.error = ""
        result.model = None
        result.generated_path = None
        result.uncertainty = None
        result.measurements = None
        result.input_series_ids = []
        result.model_seg_series_uid = ""
        result.model_seg_sop_uid = ""
        result.save()

    _discard(study, previous_mask, previous_seg)
    return result


def _discard(study: Study, mask_key: str | None, seg_series_uid: str) -> None:
    """Remove the files of a replaced result; a leftover is logged, not fatal."""
    try:
        if mask_key:
            delete_object(BUCKET_MASKS, mask_key)
        if seg_series_uid:
            OrthancClient().delete_series(seg_series_uid)
    except (StorageError, OrthancUnavailable) as exc:
        logger.warning("segmentation.run: study %s: previous result not removed: %s", study.id, exc)


def _ensure_study(study: Study) -> None:
    """Checked before anything is stored: a deleted study must not get its SEG back in Orthanc."""
    if not Study.objects.filter(pk=study.pk).exists():
        raise StudyGone(f"Study {study.pk} was deleted during segmentation")


def _fail(result: SegmentationResult, reason: str) -> None:
    result.status = StatusChoices.FAILED
    result.error = reason
    try:
        result.save(update_fields=["status", "error", "input_series_ids", "updated_at"])
    except DatabaseError:  # the study and its row were deleted meanwhile
        logger.warning("segmentation.run: result %s is gone, failure not saved", result.pk)


def _is_empty(mask_path: Path) -> bool:
    return not np.asarray(nib.load(mask_path).dataobj).any()


def _calculate_uncertainty(prob_map_path: Path) -> float | None:
    """Oblicza średnią entropię na mapie prawdopodobieństwa wewnątrz obszaru guza."""
    try:
        prob_img = nib.load(prob_map_path)
        probs = prob_img.get_fdata()
        # Entropia Shannon: -p * log(p) - (1-p) * log(1-p)
        eps = 1e-7
        probs = np.clip(probs, eps, 1.0 - eps)
        entropy = -(probs * np.log2(probs) + (1.0 - probs) * np.log2(1.0 - probs))
        mask = probs > 0.05

        if np.any(mask):
            return float(np.mean(entropy[mask]))

        return None
    except Exception as exc:
        logger.warning("Nie udało się wyliczyć entropii z %s: %s", prob_map_path, exc)
        return None


@app.task(name="segmentation.run", bind=True, queue="segmentation")
def run(self, study_id: str) -> None:
    """Segment one study: Orthanc DICOM → NIfTI → nnU-Net mask in the masks bucket.

    A non-empty mask is also stored in Orthanc as DICOM SEG, so the review viewer can show it.
    """
    result = _start(int(study_id))
    if result is None:
        return
    study = result.study
    try:
        if not study.orthanc_path:
            raise OrthancUnavailable(f"Study {study.id} has no Orthanc id")

        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            case_id = f"study_{study.id}"
            orthanc = OrthancClient()
            orthanc.download_study(study.orthanc_path, root / "dicom")

            converted = convert_study(root / "dicom", case_id, root / "nifti")
            result.input_series_ids = _series_ids(converted.manifest)

            if converted.status is not Status.OK:
                reason = converted.manifest.get("geometry_error") or str(converted.status)
                raise SegmentationError(f"DICOM conversion status {converted.status}: {reason}")

            model = _model()
            prediction = model.predict(
                [converted.nifti[role] for role in CHANNELS],
                root / "prediction",
                case_id,
            )

            _ensure_study(study)
            label_key = f"{study.id}/{prediction.label_path.name}"
            prob_key = f"{study.id}/{prediction.probabilities_path.name}"

            upload_file(prediction.label_path, BUCKET_MASKS, label_key)
            upload_file(prediction.probabilities_path, BUCKET_MASKS, prob_key)

            # the study is already on disk, so the SEG costs no second download
            if not _is_empty(prediction.label_path):
                seg = convert_nifti_to_dicom_seg(
                    study_dir=root / "dicom",
                    mask_nifti_path=prediction.label_path,
                    output_seg_path=root / "model_seg.dcm",
                    segment_label="Breast Lesion",
                    algorithm=Algorithm(model.info.name, model.info.version),
                )
                _ensure_study(study)
                orthanc.upload_dicom_file(seg.path)
                result.model_seg_series_uid = seg.series_instance_uid
                result.model_seg_sop_uid = seg.sop_instance_uid

            result.generated_path = label_key
            result.measurements = measure_file(prediction.label_path)
            result.uncertainty = _calculate_uncertainty(prediction.probabilities_path)
            result.model = _model_version(model)
            result.status = StatusChoices.COMPLETED
            result.save(
                update_fields=[
                    "status",
                    "generated_path",
                    "input_series_ids",
                    "uncertainty",
                    "model",
                    "model_seg_series_uid",
                    "model_seg_sop_uid",
                    "measurements",
                    "updated_at",
                ]
            )

    except StudyGone as exc:
        # only a safeguard: a study is not deleted while its segmentation is PROCESSING
        logger.warning("segmentation.run: %s", exc)
    except (SegmentationError, OrthancUnavailable) as exc:
        _fail(result, str(exc))
        logger.error("segmentation.run: study %s: %s", study_id, exc)
        raise
    except Exception as exc:
        _fail(result, f"{type(exc).__name__}: {exc}")
        logger.exception("segmentation.run failed for study %s", study_id)
        raise


def _corrected_key(study: Study) -> str:
    # One corrected mask per study, so a repeated run overwrites it instead of adding a file.
    return f"{study.id}/study_{study.id}_corrected.nii.gz"


def _series_file(study_dir: Path, series_uid: str) -> Path:
    """The file of a single-instance series (a SEG) among the downloaded study."""
    for path in sorted(study_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            dataset = pydicom.dcmread(path, stop_before_pixels=True)
        except InvalidDicomError:
            continue
        if dataset.get("SeriesInstanceUID") == series_uid:
            return path
    raise FileNotFoundError(f"Series {series_uid} is not in the study downloaded from Orthanc")


@app.task(name="segmentation.correction_from_dicom_seg", queue="segmentation-convert")
def correction_from_dicom_seg(result_id: int) -> None:
    """Turn the radiologist's corrected mask into the model's format (CPU queue, ADR 0004).

    The SEG drawn in the viewer is already in Orthanc (``approved_seg_series_uid``); it becomes a
    NIfTI on the grid of the model's mask in the masks bucket (``accepted_path``), and the
    measurements are taken from it. The status stays CORRECTED; a failure is kept in ``error``.
    """
    result = SegmentationResult.objects.select_related("study").filter(pk=result_id).first()
    if result is None:
        logger.warning("correction_from_dicom_seg: result %s does not exist, skipped", result_id)
        return
    seg_uid = result.approved_seg_series_uid
    if result.status != StatusChoices.CORRECTED or not seg_uid:
        logger.info(
            "correction_from_dicom_seg: result %s is %s without a corrected SEG, skipped",
            result_id,
            result.status,
        )
        return
    study = result.study

    try:
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            dicom_dir, nifti_path = root / "dicom", root / "corrected.nii.gz"
            OrthancClient().download_study(study.orthanc_path, dicom_dir)
            convert_dicom_seg_to_nifti(_series_file(dicom_dir, seg_uid), dicom_dir, nifti_path)
            measurements = measure_file(nifti_path)
            key = _corrected_key(study)
            upload_file(nifti_path, BUCKET_MASKS, key)
    except Exception as exc:
        _correction_failed(result_id, seg_uid, f"{type(exc).__name__}: {exc}")
        logger.exception("correction_from_dicom_seg failed for result %s", result_id)
        raise

    with transaction.atomic():
        current = SegmentationResult.objects.select_for_update().filter(pk=result_id).first()
        # reopened or corrected again meanwhile: this conversion is no longer the one wanted
        if current is None or current.approved_seg_series_uid != seg_uid:
            logger.info(
                "correction_from_dicom_seg: result %s changed meanwhile, not saved", result_id
            )
            return
        current.accepted_path = key
        current.measurements = measurements
        current.error = ""
        current.save(update_fields=["accepted_path", "measurements", "error", "updated_at"])
    logger.info("correction_from_dicom_seg: result %s stored as %s", result_id, key)


def _correction_failed(result_id: int, seg_uid: str, reason: str) -> None:
    SegmentationResult.objects.filter(pk=result_id, approved_seg_series_uid=seg_uid).update(
        error=reason
    )
