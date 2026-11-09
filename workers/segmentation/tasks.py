from config.celery import app
from patients.models import Study
from segmentation.models import SegmentationResult, StatusChoices

@app.task(name="segmentation.run")
def run(study_id: str) -> None:

    study = Study.objects.filter(id=int(study_id)).first()

    SegmentationResult.objects.create(
        study=study,
        status=StatusChoices.COMPLETED,
        uncertainty=0.15,
    )
    return


@app.task(name="segmentation.correction_to_dicom_seg")
def correction_to_dicom_seg(study_instance_uid: str, mask_key: str) -> None:
    raise NotImplementedError
