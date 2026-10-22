from config.celery import app


@app.task(name="segmentation.run")
def run(study_id: str) -> None:
    raise NotImplementedError


@app.task(name="segmentation.correction_to_dicom_seg")
def correction_to_dicom_seg(study_instance_uid: str, mask_key: str) -> None:
    raise NotImplementedError
