import logging
import os
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np
from common.storage import BUCKET_MASKS, download_file, upload_file
from config.celery import app
from mlops.models import ModelVersion
from patients.models import Study
from patients.orthanc_client import (
    OrthancClient,
    OrthancUnavailable,
    OrthancUnauthorized,
    StudyNotFound,
)
from segmentation.models import SegmentationResult, StatusChoices

from workers.segmentation.channels import CHANNELS
from workers.segmentation.conversion import (
    Algorithm,
    Status,
    convert_nifti_to_dicom_seg,
    convert_study,
)
from workers.segmentation.models.base import SegmentationError, SegmentationModel
from workers.segmentation.models.registry import get_segmentation_model

logger = logging.getLogger(__name__)

MODEL_DIR_ENV = "SEGMENTATION_MODEL_DIR"

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


def _reject(result: SegmentationResult) -> None:
    result.status = StatusChoices.REJECTED
    result.save(update_fields=["status", "input_series_ids"])


def _is_empty(mask_path: Path) -> bool:
    return not np.asarray(nib.load(mask_path).dataobj).any()


def _calculate_uncertainty(prob_map_path: Path) -> float:
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

        return 0.0
    except Exception as exc:
        logger.warning("Nie udało się wyliczyć entropii z %s: %s", prob_map_path, exc)
        return 0.0


@app.task(name="segmentation.run", bind=True, queue="segmentation")
def run(self, study_id: str) -> None:
    """Segment one study: Orthanc DICOM → NIfTI → nnU-Net mask in the masks bucket.

    A non-empty mask is also stored in Orthanc as DICOM SEG, so the review viewer can show it.
    """
    study = Study.objects.get(pk=int(study_id))
    result = SegmentationResult.objects.create(study=study, status=StatusChoices.PROCESSING)
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
                orthanc.upload_dicom_file(seg.path)
                result.model_seg_series_uid = seg.series_instance_uid
                result.model_seg_sop_uid = seg.sop_instance_uid

            result.generated_path = label_key
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
                ]
            )

    except (SegmentationError, OrthancUnavailable) as exc:
        _reject(result)
        logger.error("segmentation.run: study %s: %s", study_id, exc)
        raise
    except Exception:
        _reject(result)
        logger.exception("segmentation.run failed for study %s", study_id)
        raise


@app.task(name="segmentation.correction_to_dicom_seg", queue="segmentation-convert")
def correction_to_dicom_seg(
    orthanc_study_id: str, mask_key: str, result_id: int | None = None
) -> None:
    """Convert an approved mask to DICOM SEG and upload it to Orthanc (CPU queue).

    ``orthanc_study_id`` is Orthanc's own study id (``Study.orthanc_path``). The UIDs of the SEG
    are saved on the SegmentationResult ``result_id``.
    """
    try:
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            dicom_dir = root / "dicom"
            mask_nifti_path = root / "corrected_mask.nii.gz"
            output_seg_path = root / "corrected_seg.dcm"

            orthanc = OrthancClient()
            orthanc.download_study(orthanc_study_id, dicom_dir)
            download_file(BUCKET_MASKS, mask_key, mask_nifti_path)

            seg = convert_nifti_to_dicom_seg(
                study_dir=dicom_dir,
                mask_nifti_path=mask_nifti_path,
                output_seg_path=output_seg_path,
                segment_label="Corrected Breast Lesion",
            )

            orthanc.upload_dicom_file(seg.path)
            if result_id is not None:
                SegmentationResult.objects.filter(pk=result_id).update(
                    approved_seg_series_uid=seg.series_instance_uid,
                    approved_seg_sop_uid=seg.sop_instance_uid,
                )

            logger.info(
                "Pomyślnie zamieniono maskę %s na DICOM SEG dla badania %s",
                mask_key,
                orthanc_study_id,
            )

    except StudyNotFound:
        logger.error("Study not found: %s", orthanc_study_id)
        raise
    except (OrthancUnavailable, OrthancUnauthorized) as exc:
        logger.error("Orthanc error: %s", exc)
        raise
    except Exception:
        logger.exception("Unexpected error during DICOM SEG conversion of %s", mask_key)
        raise
