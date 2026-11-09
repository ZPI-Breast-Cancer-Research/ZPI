import logging
import os
import tempfile
from pathlib import Path

from common.storage import BUCKET_MASKS, upload_file
from config.celery import app
from patients.models import Study
from patients.orthanc_client import OrthancClient, OrthancUnavailable
from segmentation.models import SegmentationResult, StatusChoices

from workers.segmentation.channels import CHANNELS
from workers.segmentation.conversion import Status, convert_study
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


@app.task(name="segmentation.run")
def run(study_id: str) -> None:
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

            model_dir = os.environ.get(MODEL_DIR_ENV)
            if not model_dir:
                raise SegmentationError(f"{MODEL_DIR_ENV} is not set")

            prediction = get_segmentation_model(Path(model_dir)).predict(
                [converted.nifti[role] for role in CHANNELS],
                root / "prediction",
                case_id,
            )
            label_key = f"{study.id}/{prediction.label_path.name}"
            upload_file(prediction.label_path, BUCKET_MASKS, label_key)
            upload_file(
                prediction.probabilities_path,
                BUCKET_MASKS,
                f"{study.id}/{prediction.probabilities_path.name}",
            )
            result.generated_path = label_key
            result.status = StatusChoices.COMPLETED
            result.save(update_fields=["status", "generated_path", "input_series_ids"])
    except (SegmentationError, OrthancUnavailable) as exc:
        _reject(result)
        logger.error("segmentation.run: study %s: %s", study_id, exc)
        raise
    except Exception:
        _reject(result)
        logger.exception("segmentation.run failed for study %s", study_id)
        raise


@app.task(name="segmentation.correction_to_dicom_seg")
def correction_to_dicom_seg(study_instance_uid: str, mask_key: str) -> None:
    raise NotImplementedError
