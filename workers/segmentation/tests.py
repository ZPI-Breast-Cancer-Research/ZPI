import pytest

from workers.segmentation.channels import CHANNELS, channel_names, channel_suffix


def test_channel_names_follow_channels_order():
    # Arrange
    expected = {"0": "pre", "1": "post1", "2": "post2"}

    # Act
    names = channel_names()

    # Assert
    assert names == expected
    assert list(names.values()) == list(CHANNELS)


def test_channel_suffix_is_zero_padded_index():
    assert [channel_suffix(role) for role in CHANNELS] == ["0000", "0001", "0002"]


def test_channel_suffix_rejects_unknown_role():
    with pytest.raises(ValueError):
        channel_suffix("post3")


# --- DICOM SEG from a mask in the model input layout -------------------------------------------

ROWS, COLUMNS, SLICES = 5, 6, 4


def _write_mr_series(directory, study_uid, frame_uid, number, acquisition_time, orientation):
    """One axial 3D MR phase; each voxel holds slice * 100 + row * 10 + column."""
    import numpy as np
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

    series_uid = generate_uid()
    sop_uids = []
    for index in range(SLICES):
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = MRImageStorage
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
        ds.SOPClassUID = MRImageStorage
        ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        ds.StudyInstanceUID = study_uid
        ds.SeriesInstanceUID = series_uid
        ds.FrameOfReferenceUID = frame_uid
        ds.PatientID, ds.PatientName, ds.PatientBirthDate, ds.PatientSex = "P1", "Test^P", "", "F"
        ds.StudyID, ds.StudyDate, ds.StudyTime, ds.AccessionNumber = "1", "20260101", "120000", ""
        ds.ReferringPhysicianName = ""
        ds.Modality, ds.Manufacturer = "MR", "Test"
        ds.SeriesNumber, ds.InstanceNumber = number, index + 1
        ds.ImageType = ["ORIGINAL", "PRIMARY", "OTHER"]
        ds.MRAcquisitionType = "3D"
        ds.AcquisitionTime = acquisition_time
        ds.ImageOrientationPatient = orientation
        ds.ImagePositionPatient = [0, 0, float(index) * 2]
        ds.PixelSpacing = [1.0, 1.0]
        ds.SliceThickness = 2.0
        ds.Rows, ds.Columns = ROWS, COLUMNS
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 0
        rows, columns = np.mgrid[0:ROWS, 0:COLUMNS]
        ds.PixelData = (index * 100 + rows * 10 + columns).astype(np.uint16).tobytes()
        ds.save_as(directory / f"{number}_{index}.dcm", enforce_file_format=True)
        sop_uids.append(ds.SOPInstanceUID)
    return sop_uids


@pytest.mark.parametrize(
    "orientation",
    [
        pytest.param([1, 0, 0, 0, 1, 0], id="training-layout-flips-axis-1"),
        pytest.param([-1, 0, 0, 0, -1, 0], id="duke-flips-axis-0"),
    ],
)
def test_dicom_seg_marks_the_same_source_voxel_as_the_nifti_mask(tmp_path, orientation):
    # Arrange
    import highdicom as hd
    import nibabel as nib
    import numpy as np
    from pydicom.uid import generate_uid

    from workers.segmentation.conversion import (
        APPROVED_SEG_SERIES_DESCRIPTION,
        Status,
        convert_nifti_to_dicom_seg,
        convert_study,
    )

    study_dir = tmp_path / "dicom"
    study_dir.mkdir()
    study_uid, frame_uid = generate_uid(), generate_uid()
    pre_sops = _write_mr_series(study_dir, study_uid, frame_uid, 1, "120000", orientation)
    _write_mr_series(study_dir, study_uid, frame_uid, 2, "120100", orientation)
    _write_mr_series(study_dir, study_uid, frame_uid, 3, "120200", orientation)

    converted = convert_study(study_dir, "case", tmp_path / "nifti")
    assert converted.status is Status.OK
    pre = nib.load(converted.nifti["pre"])
    voxel = (1, 0, 2)
    code = int(np.asarray(pre.dataobj)[voxel])
    source_slice, source_row, source_column = code // 100, code // 10 % 10, code % 10

    mask = np.zeros(pre.shape, dtype=np.uint8)
    mask[voxel] = 1
    mask_path = tmp_path / "mask.nii.gz"
    nib.save(nib.Nifti1Image(mask, pre.affine), mask_path)

    # Act
    written = convert_nifti_to_dicom_seg(study_dir, mask_path, tmp_path / "seg.dcm")

    # Assert
    seg = hd.seg.segread(written.path)
    assert seg.SeriesDescription == APPROVED_SEG_SERIES_DESCRIPTION
    assert seg.SegmentSequence[0].SegmentAlgorithmType == "MANUAL"
    assert (seg.SeriesInstanceUID, seg.SOPInstanceUID) == (
        written.series_instance_uid,
        written.sop_instance_uid,
    )
    frames = seg.pixel_array.reshape(-1, ROWS, COLUMNS)  # a single frame comes back as 2D
    marked = [
        (frame, item)
        for frame, item in zip(frames, seg.PerFrameFunctionalGroupsSequence, strict=True)
        if frame.any()
    ]
    assert len(marked) == 1
    frame, item = marked[0]
    source_sop = item.DerivationImageSequence[0].SourceImageSequence[0].ReferencedSOPInstanceUID
    assert source_sop == pre_sops[source_slice]
    assert [tuple(map(int, rc)) for rc in zip(*np.nonzero(frame))] == [(source_row, source_column)]


# --- segmentation.run and segmentation.correction_to_dicom_seg ----------------------------------

AXIAL = [1, 0, 0, 0, 1, 0]


class FakeOrthanc:
    """Serves a synthetic three-phase study and keeps what was uploaded."""

    fail_upload = False

    def __init__(self):
        self.uploaded = []

    def download_study(self, orthanc_id, destination):
        from pydicom.uid import generate_uid

        destination.mkdir(parents=True, exist_ok=True)
        study_uid, frame_uid = generate_uid(), generate_uid()
        for number, time in ((1, "120000"), (2, "120100"), (3, "120200")):
            _write_mr_series(destination, study_uid, frame_uid, number, time, AXIAL)

    def upload_dicom_file(self, path):
        import pydicom
        from patients.orthanc_client import OrthancUnavailable

        if FakeOrthanc.fail_upload:
            raise OrthancUnavailable("Orthanc upload response invalid: 400")
        self.uploaded.append(pydicom.dcmread(path))
        return {"Status": "Success"}


class FakeModel:
    """Writes a mask over the pre phase grid: one voxel, or nothing when ``empty``."""

    def __init__(self, empty=False):
        from workers.segmentation.models.base import ModelInfo

        self.empty = empty
        self.info = ModelInfo("nnunet", "dce3-test", "7", ("pre", "post1", "post2"), {})

    def predict(self, channels, out_dir, case_id):
        import nibabel as nib
        import numpy as np

        from workers.segmentation.models.base import SegmentationResult as Prediction

        out_dir.mkdir(parents=True, exist_ok=True)
        pre = nib.load(channels[0])
        mask = np.zeros(pre.shape, dtype=np.uint8)
        if not self.empty:
            mask[1, 0, 2] = 1
        label_path, probabilities_path = (
            out_dir / f"{case_id}.nii.gz",
            out_dir / f"{case_id}_prob.nii.gz",
        )
        nib.save(nib.Nifti1Image(mask, pre.affine), label_path)
        nib.save(nib.Nifti1Image(mask.astype(np.float32), pre.affine), probabilities_path)
        return Prediction(label_path, probabilities_path, self.info.name, self.info.version, 1.0)


@pytest.fixture
def pipeline(monkeypatch):
    """segmentation tasks with a fake Orthanc, model and masks bucket."""
    from workers.segmentation import tasks

    orthanc = FakeOrthanc()
    FakeOrthanc.fail_upload = False
    stored = {}
    monkeypatch.setattr(tasks, "OrthancClient", lambda: orthanc)
    monkeypatch.setattr(
        tasks, "upload_file", lambda path, bucket, key: stored.update({key: path.read_bytes()})
    )
    monkeypatch.setattr(tasks, "_model", lambda: FakeModel())
    return tasks, orthanc, stored


@pytest.fixture
def study(db):
    from patients.models import Study

    return Study.objects.create(orthanc_path="orthanc-study-1")


def test_run_stores_the_model_mask_as_dicom_seg(pipeline, study):
    # Arrange
    tasks, orthanc, _ = pipeline

    # Act
    tasks.run(str(study.id))

    # Assert
    result = study.segmentations.get()
    assert result.status == "COMPLETED"
    [seg] = orthanc.uploaded
    assert seg.Modality == "SEG"
    assert seg.SeriesDescription == "MARIA model segmentation"
    segment = seg.SegmentSequence[0]
    assert segment.SegmentAlgorithmType == "AUTOMATIC"
    assert segment.SegmentAlgorithmName == "dce3-test"
    assert segment.SegmentationAlgorithmIdentificationSequence[0].AlgorithmVersion == "7"
    assert (result.model_seg_series_uid, result.model_seg_sop_uid) == (
        seg.SeriesInstanceUID,
        seg.SOPInstanceUID,
    )
    # the fake model marks a single voxel: tiny volume, but it has dimensions
    assert result.measurements["volume_ml"] >= 0
    assert len(result.measurements["dimensions_mm"]) == 3


def test_run_with_an_empty_mask_stores_no_seg(pipeline, study, monkeypatch):
    # Arrange
    tasks, orthanc, stored = pipeline
    monkeypatch.setattr(tasks, "_model", lambda: FakeModel(empty=True))

    # Act
    tasks.run(str(study.id))

    # Assert
    result = study.segmentations.get()
    assert result.status == "COMPLETED"
    assert orthanc.uploaded == []
    assert result.model_seg_series_uid == result.model_seg_sop_uid == ""
    assert result.generated_path in stored
    assert result.measurements == {"volume_ml": 0.0, "largest_volume_ml": 0.0, "dimensions_mm": None}


def test_run_rejects_the_result_when_orthanc_refuses_the_seg(pipeline, study):
    # Arrange
    from patients.orthanc_client import OrthancUnavailable

    tasks, _, stored = pipeline
    FakeOrthanc.fail_upload = True

    # Act
    with pytest.raises(OrthancUnavailable):
        tasks.run(str(study.id))

    # Assert
    result = study.segmentations.get()
    assert result.status == "REJECTED"
    assert result.model_seg_series_uid == ""
    assert f"{study.id}/study_{study.id}.nii.gz" in stored


def test_approval_saves_the_uids_of_the_approved_seg(pipeline, study, monkeypatch):
    # Arrange
    from segmentation.models import SegmentationResult

    tasks, orthanc, stored = pipeline
    tasks.run(str(study.id))
    result = study.segmentations.get()
    model_seg = orthanc.uploaded.pop()
    mask_bytes = stored[result.generated_path]
    monkeypatch.setattr(
        tasks, "download_file", lambda bucket, key, path: path.write_bytes(mask_bytes)
    )

    # Act
    tasks.correction_to_dicom_seg(study.orthanc_path, result.generated_path, result_id=result.id)

    # Assert
    result = SegmentationResult.objects.get(pk=result.pk)
    [seg] = orthanc.uploaded
    assert seg.SeriesDescription == "MARIA approved segmentation"
    assert seg.SegmentSequence[0].SegmentAlgorithmType == "MANUAL"
    assert (result.approved_seg_series_uid, result.approved_seg_sop_uid) == (
        seg.SeriesInstanceUID,
        seg.SOPInstanceUID,
    )
    assert result.approved_seg_series_uid != model_seg.SeriesInstanceUID
    assert result.model_seg_series_uid == model_seg.SeriesInstanceUID


# --- measurements ---


def _box(shape=(20, 20, 20)):
    import numpy as np

    mask = np.zeros(shape, dtype=np.uint8)
    mask[2:12, 2:7, 2:4] = 1  # 10 x 5 x 2 voxels
    return mask


def test_measure_gives_volume_in_ml_and_dimensions_in_mm_longest_first():
    import numpy as np

    from workers.segmentation.measurements import measure

    affine = np.diag([0.5, 1.0, 2.0, 1.0])  # voxel of 1 mm³

    result = measure(_box(), affine)

    assert result == {"volume_ml": 0.1, "largest_volume_ml": 0.1, "dimensions_mm": [5.0, 5.0, 4.0]}


def test_measure_takes_dimensions_from_the_largest_region_and_volume_from_all():
    import numpy as np

    from workers.segmentation.measurements import measure

    mask = _box()
    mask[18, 18, 18] = 1  # a small false region far away

    result = measure(mask, np.eye(4))

    assert result["dimensions_mm"] == [10.0, 5.0, 2.0]
    assert result["volume_ml"] == 0.1  # 101 voxels of 1 mm³, rounded
    assert result["largest_volume_ml"] == 0.1  # 100 voxels; the false region is one more


def test_measure_gives_the_volume_of_the_largest_region_apart_from_the_total():
    import numpy as np

    from workers.segmentation.measurements import measure

    mask = np.zeros((40, 40, 40), dtype=np.uint8)
    mask[1:21, 1:21, 1:6] = 1  # 2000 voxels of 1 mm³
    mask[30:35, 30:35, 30:35] = 1  # 125 voxels, a second part

    result = measure(mask, np.eye(4))

    assert result["volume_ml"] == 2.12
    assert result["largest_volume_ml"] == 2.0


def test_measure_of_an_empty_mask():
    import numpy as np

    from workers.segmentation.measurements import measure

    assert measure(np.zeros((5, 5, 5)), np.eye(4)) == {
        "volume_ml": 0.0,
        "largest_volume_ml": 0.0,
        "dimensions_mm": None,
    }
