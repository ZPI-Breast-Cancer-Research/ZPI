import io
import zipfile

import pytest

from patients.views import (
    _orthanc_study_id,
    _pick_uncertainty,
    _check_archive,
    _load_state,
)
from patients.models import Study
from extraction.models import ExtractionResult
from segmentation.models import SegmentationResult


# -------------------------------------------------
# _orthanc_study_id
# -------------------------------------------------

@pytest.mark.parametrize(
    "response, expected",
    [
        ({"ID": "study123"}, "study123"),
        ({"ParentStudy": "study456"}, "study456"),
        ([{"ID": "study789"}], "study789"),
        ([{"ParentStudy": "study999"}], "study999"),
        ([], None),
        (None, None),
        ("study123", "study123"),
    ],
)
def test_orthanc_study_id(response, expected):
    assert _orthanc_study_id(response) == expected


# -------------------------------------------------
# _pick_uncertainty
# -------------------------------------------------

class DummyResult:
    def __init__(self, uncertainty):
        self.uncertainty = uncertainty


def test_pick_uncertainty_segmentation_has_priority():
    segmentation = DummyResult(0.2)
    extraction = DummyResult(0.8)

    assert _pick_uncertainty(segmentation, extraction) == 0.2


def test_pick_uncertainty_falls_back_to_extraction():
    segmentation = DummyResult(None)
    extraction = DummyResult(0.7)

    assert _pick_uncertainty(segmentation, extraction) == 0.7


def test_pick_uncertainty_returns_none():
    segmentation = DummyResult(None)
    extraction = DummyResult(None)

    assert _pick_uncertainty(segmentation, extraction) is None


def test_pick_uncertainty_without_segmentation():
    extraction = DummyResult(0.4)

    assert _pick_uncertainty(None, extraction) == 0.4


def test_pick_uncertainty_without_results():
    assert _pick_uncertainty(None, None) is None


# -------------------------------------------------
# _check_archive
# -------------------------------------------------

def create_zip(files):
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w") as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)

    return buffer.getvalue()


def create_dicom_bytes(study_uid):
    import pydicom
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage

    buffer = io.BytesIO()

    file_meta = FileMetaDataset()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = f"{study_uid}.1"

    ds = FileDataset(
        None,
        {},
        file_meta=file_meta,
        preamble=b"\0" * 128,
    )

    ds.StudyInstanceUID = study_uid
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = f"{study_uid}.1"

    ds.save_as(buffer, enforce_file_format=True)

    return buffer.getvalue()


def test_check_archive_rejects_invalid_zip():
    response = _check_archive(b"not a zip")

    assert response.status_code == 400
    assert response.data["detail"] == "Not correct ZIP file archive."


def test_check_archive_rejects_empty_zip():
    archive = create_zip({})

    response = _check_archive(archive)

    assert response.status_code == 400
    assert response.data["detail"] == "No files in archive."


def test_check_archive_rejects_non_dicom_files():
    archive = create_zip({
        "document.txt": b"Hello world",
    })

    response = _check_archive(archive)

    assert response.status_code == 400
    assert response.data["detail"] == (
        "No valid DICOM metadata found in archive files."
    )


def test_check_archive_accepts_one_study():
    dicom = create_dicom_bytes("1.2.3.4.5")

    archive = create_zip({
        "image1.dcm": dicom,
        "image2.dcm": dicom,
    })

    response = _check_archive(archive)

    assert response is None


def test_check_archive_rejects_multiple_studies():
    dicom1 = create_dicom_bytes("1.2.3.4.5")
    dicom2 = create_dicom_bytes("1.2.3.4.6")

    archive = create_zip({
        "image1.dcm": dicom1,
        "image2.dcm": dicom2,
    })

    response = _check_archive(archive)

    assert response.status_code == 400
    assert response.data["code"] == "multiple_studies_error"


# -------------------------------------------------
# _load_state
# -------------------------------------------------

# @pytest.mark.django_db
# def test_load_state_returns_latest_extraction(study):
#     old_result = ExtractionResult.objects.create(
#         study=study,
#         status="PENDING",
#         uncertainty=0.8,
#     )

#     latest_result = ExtractionResult.objects.create(
#         study=study,
#         status="COMPLETED",
#         uncertainty=0.2,
#     )

#     state = _load_state([{"orthanc_id": study.orthanc_path}])

#     assert state[1][0].id == latest_result.id
#     assert state[1][0].id != old_result.id


# @pytest.mark.django_db
# def test_load_state_returns_latest_segmentation(study):
#     old_result = SegmentationResult.objects.create(
#         study=study,
#         status="PENDING",
#         uncertainty=0.8,
#     )

#     latest_result = SegmentationResult.objects.create(
#         study=study,
#         status="COMPLETED",
#         uncertainty=0.1,
#     )

#     state = _load_state([{"orthanc_id": study.orthanc_path}])

#     assert state[study.id]["segmentation"].id == latest_result.id
#     assert state[study.id]["segmentation"].id != old_result.id


# @pytest.mark.django_db
# def test_load_state_returns_none_when_results_do_not_exist(study):
#     state = _load_state([{"orthanc_id": study.orthanc_path}])

#     assert state[study.id]["extraction"] is None
#     assert state[study.id]["segmentation"] is None