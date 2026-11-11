"""Synthetic MR breast DICOMs for local development, uploaded to Orthanc over REST."""

import io
import uuid

import numpy as np
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import PYDICOM_IMPLEMENTATION_UID, ExplicitVRLittleEndian

MR_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.4"
PATIENT_ID_PREFIX = "DEMO-P"
SIZE = 64
SLICES = 10
SERIES = (
    (1, "Przed kontrastem"),
    (2, "Po kontraście"),
    (3, "Subtrakcja"),
)
TIMEOUT = (2, 30)
_NAMESPACE = uuid.UUID("6f2b1a54-8c3e-4a53-9e55-0d6c1d4b7a10")


def make_uid(*parts) -> str:
    """Deterministic UID, so re-running the seed does not create duplicates."""
    return "2.25." + str(uuid.uuid5(_NAMESPACE, "|".join(map(str, parts))).int)


def build_volumes(number: int) -> dict[int, np.ndarray]:
    """A fake breast: ellipsoid tissue plus one enhancing lesion."""
    rng = np.random.default_rng(number)
    zz, yy, xx = np.mgrid[0:SLICES, 0:SIZE, 0:SIZE].astype(np.float32)

    body = (
        ((xx - SIZE / 2) / (SIZE * 0.42)) ** 2
        + ((yy - SIZE / 2) / (SIZE * 0.46)) ** 2
        + ((zz - SLICES / 2) / (SLICES * 0.62)) ** 2
    ) <= 1.0
    noise = rng.normal(0.0, 0.02, body.shape).astype(np.float32)
    tissue = 0.30 + 0.12 * np.sin(xx / 9.0) * np.cos(yy / 11.0)
    pre = np.where(body, tissue, 0.02) + noise

    cx = rng.uniform(0.35, 0.70) * SIZE
    cy = rng.uniform(0.35, 0.65) * SIZE
    cz = rng.uniform(0.30, 0.70) * SLICES
    rx, ry, rz = rng.uniform(4, 8), rng.uniform(4, 8), rng.uniform(1.8, 3.2)
    lesion = (
        ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 + ((zz - cz) / rz) ** 2
    ) <= 1.0

    post = pre + np.where(lesion, 0.55, np.where(body, 0.05, 0.0))
    subtraction = np.clip(post - pre, 0.0, None)

    def to_u16(array):
        return (np.clip(array, 0.0, 1.2) / 1.2 * 4095).astype("<u2")

    return {1: to_u16(pre), 2: to_u16(post), 3: to_u16(subtraction)}


def _instance_bytes(
    *, patient_id, birth_date, study_uid, study_date,
    series_uid, series_number, series_description, index, pixels,
) -> bytes:
    sop_uid = make_uid(series_uid, "instance", index)

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = MR_IMAGE_STORAGE
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID

    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    ds.SpecificCharacterSet = "ISO_IR 192"  # UTF-8 (polskie znaki w opisach serii)
    ds.SOPClassUID = MR_IMAGE_STORAGE
    ds.SOPInstanceUID = sop_uid
    ds.PatientID = patient_id
    ds.PatientName = f"DEMO^{patient_id}"
    ds.PatientSex = "F"
    ds.PatientBirthDate = birth_date
    ds.StudyInstanceUID = study_uid
    ds.StudyDate = study_date
    ds.StudyTime = "120000"
    ds.StudyDescription = "MR piersi z kontrastem"
    ds.StudyID = "1"
    ds.AccessionNumber = patient_id
    ds.Modality = "MR"
    ds.SeriesInstanceUID = series_uid
    ds.SeriesNumber = series_number
    ds.SeriesDescription = series_description
    ds.FrameOfReferenceUID = make_uid(study_uid, "frame")
    ds.InstanceNumber = index + 1
    ds.ImagePositionPatient = [0.0, 0.0, float(index) * 3.0]
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.PixelSpacing = [1.5, 1.5]
    ds.SliceThickness = 3.0
    ds.Rows, ds.Columns = pixels.shape
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PixelData = pixels.tobytes()

    buffer = io.BytesIO()
    ds.save_as(buffer)
    return buffer.getvalue()


def upload_study(session, base_url, auth, *, number: int, study_date):
    """Uploads one synthetic study. Returns (orthanc_study_id, [SeriesInstanceUID, ...])."""
    patient_id = f"{PATIENT_ID_PREFIX}{number:04d}"
    study_uid = make_uid("demo-study", number)
    age = 35 + (number * 7) % 40
    birth_date = f"{study_date.year - age}0101"
    volumes = build_volumes(number)

    orthanc_id = None
    series_uids = []
    for series_number, description in SERIES:
        series_uid = make_uid(study_uid, "series", series_number)
        series_uids.append(series_uid)
        for index in range(SLICES):
            payload = _instance_bytes(
                patient_id=patient_id,
                birth_date=birth_date,
                study_uid=study_uid,
                study_date=study_date.strftime("%Y%m%d"),
                series_uid=series_uid,
                series_number=series_number,
                series_description=description,
                index=index,
                pixels=volumes[series_number][index],
            )
            response = session.post(
                f"{base_url}/instances",
                data=payload,
                auth=auth,
                headers={"Content-Type": "application/dicom"},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            orthanc_id = response.json()["ParentStudy"]
    return orthanc_id, series_uids


def delete_demo_studies(session, base_url, auth) -> int:
    response = session.post(
        f"{base_url}/tools/find",
        json={"Level": "Study", "Query": {"PatientID": f"{PATIENT_ID_PREFIX}*"}},
        auth=auth,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    ids = response.json()
    for orthanc_id in ids:
        session.delete(
            f"{base_url}/studies/{orthanc_id}", auth=auth, timeout=TIMEOUT
        ).raise_for_status()
    return len(ids)
