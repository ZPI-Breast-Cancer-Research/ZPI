import logging
import os
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np
from common.storage import BUCKET_MASKS, download_file, upload_file
from config.celery import app
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
    Status,
    convert_nifti_to_dicom_seg,
    convert_study,
)
from workers.segmentation.models.base import SegmentationError
from workers.segmentation.models.registry import get_segmentation_model

logger = logging.getLogger(__name__)

MODEL_DIR_ENV = "SEGMENTATION_MODEL_DIR"


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
    """Segment one study: Orthanc DICOM → NIfTI → nnU-Net mask in the masks bucket."""
    study = Study.objects.get(pk=int(study_id))
    result = SegmentationResult.objects.create(study=study, status=StatusChoices.PROCESSING)
    try:
        if not study.orthanc_path:
            raise OrthancUnavailable(f"Study {study.id} has no Orthanc id")

        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            case_id = f"study_{study.id}"
            OrthancClient().download_study(study.orthanc_path, root / "dicom")

            converted = convert_study(root / "dicom", case_id, root / "nifti")
            result.input_series_ids = _series_ids(converted.manifest)

            if converted.status is not Status.OK:
                reason = converted.manifest.get("geometry_error") or str(converted.status)
                raise SegmentationError(f"DICOM conversion status {converted.status}: {reason}")

            model_dir = os.getenv(MODEL_DIR_ENV)
            if not model_dir:
                logger.error("Environment variable %s is not set", MODEL_DIR_ENV)
                raise SegmentationError(f"Environment variable {MODEL_DIR_ENV} is not set")

            model_path = Path(model_dir)
            model = get_segmentation_model(model_path)

            prediction = model.predict(
                [converted.nifti[role] for role in CHANNELS],
                root / "prediction",
                case_id,
            )

            label_key = f"{study.id}/{prediction.label_path.name}"
            prob_key = f"{study.id}/{prediction.probabilities_path.name}"

            upload_file(prediction.label_path, BUCKET_MASKS, label_key)
            upload_file(prediction.probabilities_path, BUCKET_MASKS, prob_key)

            uncertainty_score = _calculate_uncertainty(prediction.probabilities_path)

            result.generated_path = label_key
            result.uncertainty = uncertainty_score
            result.model_version = getattr(model, "version", model_path.name)
            result.status = StatusChoices.COMPLETED
            
            result.save(
                update_fields=[
                    "status",
                    "generated_path",
                    "input_series_ids",
                    "uncertainty",
                    "model_version",
                ]
            )

    except (SegmentationError, OrthancUnavailable) as exc:
        _reject(result)
        logger.error("segmentation.run: study %s: %s", study_id, exc)
        raise
    except Exception as exc:
        logger.error("Unexpected error: %s", exc)
        _reject(result)
        logger.exception("segmentation.run failed for study %s", study_id)
        raise


@app.task(name="segmentation.correction_to_dicom_seg", queue="segmentation-convert")
def correction_to_dicom_seg(study_instance_uid: str, mask_key: str) -> None:
    """Convert a corrected mask back to DICOM SEG format and upload to Orthanc (CPU queue)."""
    try:
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            dicom_dir = root / "dicom"
            mask_nifti_path = root / "corrected_mask.nii.gz"
            output_seg_path = root / "corrected_seg.dcm"

            orthanc = OrthancClient()

            orthanc.download_all_instances(study_instance_uid, dicom_dir)

            download_file(BUCKET_MASKS, mask_key, mask_nifti_path)

            convert_nifti_to_dicom_seg(
                ref_dicom_dir=dicom_dir,
                mask_nifti_path=mask_nifti_path,
                output_seg_path=output_seg_path,
                segment_label="Corrected Breast Lesion",
            )

            orthanc.upload_dicom_file(output_seg_path)

            logger.info(
                "Pomyślnie zamieniono maskę %s na DICOM SEG dla badania %s",
                mask_key,
                study_instance_uid,
            )

    except StudyNotFound:
        logger.error("Study not found: %s", study_instance_uid)
        raise
    except (OrthancUnavailable, OrthancUnauthorized) as exc:
        logger.error("Orthanc error: %s", exc)
        raise
    except Exception as exc:
        logger.error("Unexpected error during DICOM SEG conversion: %s", exc)
        raise
