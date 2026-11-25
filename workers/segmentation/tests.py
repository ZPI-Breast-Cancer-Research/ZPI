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
    assert [tuple(map(int, rc)) for rc in zip(*np.nonzero(frame), strict=True)] == [
        (source_row, source_column)
    ]


# --- a mask in the model input layout from a DICOM SEG -------------------------------------------


def _three_phases(tmp_path, orientation=None):
    """A study of three phases; returns its directory and the `pre` NIfTI from convert_study."""
    import nibabel as nib
    from pydicom.uid import generate_uid

    from workers.segmentation.conversion import Status, convert_study

    orientation = orientation or [1, 0, 0, 0, 1, 0]
    study_dir = tmp_path / "dicom"
    study_dir.mkdir()
    study_uid, frame_uid = generate_uid(), generate_uid()
    for number, time in ((1, "120000"), (2, "120100"), (3, "120200")):
        _write_mr_series(study_dir, study_uid, frame_uid, number, time, orientation)
    converted = convert_study(study_dir, "case", tmp_path / "nifti")
    assert converted.status is Status.OK
    return study_dir, nib.load(converted.nifti["pre"])


def _asymmetric_mask(shape):
    """Voxels on two slices only, none of them mirrored: a wrong flip or slice order moves them."""
    import numpy as np

    mask = np.zeros(shape, dtype=np.uint8)
    mask[0, 1, 0] = mask[1, 1, 0] = mask[4, 2, 3] = 1
    return mask


@pytest.mark.parametrize(
    "orientation",
    [
        pytest.param([1, 0, 0, 0, 1, 0], id="training-layout-flips-axis-1"),
        pytest.param([-1, 0, 0, 0, -1, 0], id="duke-flips-axis-0"),
    ],
)
def test_a_seg_comes_back_as_the_mask_it_was_written_from(tmp_path, orientation):
    # Arrange: the model's mask written as a SEG, as segmentation.run does
    import nibabel as nib
    import numpy as np

    from workers.segmentation.conversion import (
        convert_dicom_seg_to_nifti,
        convert_nifti_to_dicom_seg,
    )

    study_dir, pre = _three_phases(tmp_path, orientation)
    mask = _asymmetric_mask(pre.shape)
    nib.save(nib.Nifti1Image(mask, pre.affine), tmp_path / "mask.nii.gz")
    seg = convert_nifti_to_dicom_seg(study_dir, tmp_path / "mask.nii.gz", tmp_path / "seg.dcm")

    # Act
    written = convert_dicom_seg_to_nifti(seg.path, study_dir, tmp_path / "back.nii.gz")

    # Assert: the same voxels on the grid of the model's NIfTI
    back = nib.load(written)
    assert np.array_equal(np.asarray(back.dataobj), mask)
    assert np.allclose(back.affine, pre.affine)


def _seg_on_series(tmp_path, study_dir, series_number, frame_uid=None):
    """A SEG drawn on one series of the study, marking a voxel of its first slice."""
    import highdicom as hd
    import numpy as np
    import pydicom
    from highdicom.sr.coding import CodedConcept

    slices = sorted(
        (pydicom.dcmread(path) for path in study_dir.glob(f"{series_number}_*.dcm")),
        key=lambda ds: ds.InstanceNumber,
    )
    pixels = np.zeros((len(slices), ROWS, COLUMNS), dtype=np.uint8)
    pixels[0, 1, 1] = 1
    seg = hd.seg.Segmentation(
        source_images=slices,
        pixel_array=pixels,
        segmentation_type=hd.seg.SegmentationTypeValues.BINARY,
        segment_descriptions=[
            hd.seg.SegmentDescription(
                segment_number=1,
                segment_label="Lesion",
                segmented_property_category=CodedConcept("49755003", "SCT", "Morphologic"),
                segmented_property_type=CodedConcept("108369006", "SCT", "Tumor"),
                algorithm_type=hd.seg.SegmentAlgorithmTypeValues.MANUAL,
            )
        ],
        series_instance_uid=pydicom.uid.generate_uid(),
        series_number=1000,
        sop_instance_uid=pydicom.uid.generate_uid(),
        instance_number=1,
        manufacturer="Test",
        manufacturer_model_name="Test",
        software_versions="1",
        device_serial_number="1",
    )
    if frame_uid:
        seg.FrameOfReferenceUID = frame_uid
    path = tmp_path / f"seg_{series_number}.dcm"
    seg.save_as(path)
    return path


def test_a_seg_drawn_on_another_phase_is_refused(tmp_path):
    # Arrange: today's viewer paints on `post`, which shares the frame of reference with `pre`
    from workers.segmentation.conversion import GeometryError, convert_dicom_seg_to_nifti

    study_dir, _ = _three_phases(tmp_path)
    seg_on_post = _seg_on_series(tmp_path, study_dir, series_number=2)

    # Act / Assert
    with pytest.raises(GeometryError, match="pre"):
        convert_dicom_seg_to_nifti(seg_on_post, study_dir, tmp_path / "back.nii.gz")
    assert not (tmp_path / "back.nii.gz").exists()


def test_a_seg_of_another_study_is_refused(tmp_path):
    # Arrange
    from pydicom.uid import generate_uid

    from workers.segmentation.conversion import GeometryError, convert_dicom_seg_to_nifti

    study_dir, _ = _three_phases(tmp_path)
    foreign = _seg_on_series(tmp_path, study_dir, series_number=1, frame_uid=generate_uid())

    # Act / Assert
    with pytest.raises(GeometryError, match="frame of reference"):
        convert_dicom_seg_to_nifti(foreign, study_dir, tmp_path / "back.nii.gz")


# --- segmentation.run and segmentation.correction_to_dicom_seg ----------------------------------

AXIAL = [1, 0, 0, 0, 1, 0]


class FakeOrthanc:
    """Serves one synthetic three-phase study, with the SEGs uploaded to it, and keeps them."""

    fail_upload = False

    def __init__(self, source):
        self.uploaded = []
        self.deleted_series = []
        self.source = source

    def download_study(self, orthanc_id, destination):
        import shutil

        from pydicom.uid import generate_uid

        if not self.source.exists():  # the same study on every download, as in Orthanc
            self.source.mkdir(parents=True)
            study_uid, frame_uid = generate_uid(), generate_uid()
            for number, time in ((1, "120000"), (2, "120100"), (3, "120200")):
                _write_mr_series(self.source, study_uid, frame_uid, number, time, AXIAL)
        shutil.copytree(self.source, destination, dirs_exist_ok=True)
        for index, dataset in enumerate(self.uploaded):
            dataset.save_as(destination / f"uploaded_{index}.dcm")

    def upload_dicom_file(self, path):
        import pydicom
        from patients.orthanc_client import OrthancUnavailable

        if FakeOrthanc.fail_upload:
            raise OrthancUnavailable("Orthanc upload response invalid: 400")
        self.uploaded.append(pydicom.dcmread(path))
        return {"Status": "Success"}

    def delete_series(self, series_instance_uid):
        self.deleted_series.append(series_instance_uid)


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
def pipeline(monkeypatch, tmp_path):
    """segmentation tasks with a fake Orthanc, model and masks bucket."""
    from workers.segmentation import tasks

    orthanc = FakeOrthanc(tmp_path / "orthanc")
    FakeOrthanc.fail_upload = False
    stored = {}
    monkeypatch.setattr(tasks, "OrthancClient", lambda: orthanc)
    monkeypatch.setattr(
        tasks, "upload_file", lambda path, bucket, key: stored.update({key: path.read_bytes()})
    )
    monkeypatch.setattr(tasks, "delete_object", lambda bucket, key: stored.pop(key, None))
    monkeypatch.setattr(tasks, "_model", lambda: FakeModel())
    return tasks, orthanc, stored


@pytest.fixture
def study(db):
    from patients.models import Study

    return Study.objects.create(orthanc_path="orthanc-study-1")


def _result(study):
    from segmentation.models import SegmentationResult

    return SegmentationResult.objects.get(study=study)


def test_run_stores_the_model_mask_as_dicom_seg(pipeline, study):
    # Arrange
    tasks, orthanc, _ = pipeline

    # Act
    tasks.run(str(study.id))

    # Assert
    result = _result(study)
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
    result = _result(study)
    assert result.status == "COMPLETED"
    assert orthanc.uploaded == []
    assert result.model_seg_series_uid == result.model_seg_sop_uid == ""
    assert result.generated_path in stored
    assert result.measurements == {
        "volume_ml": 0.0,
        "largest_volume_ml": 0.0,
        "dimensions_mm": None,
    }
    assert result.uncertainty is None  # unknown, so the case goes to the top of the review queue


def test_run_marks_the_result_failed_when_orthanc_refuses_the_seg(pipeline, study):
    # Arrange
    from patients.orthanc_client import OrthancUnavailable

    tasks, _, stored = pipeline
    FakeOrthanc.fail_upload = True

    # Act
    with pytest.raises(OrthancUnavailable):
        tasks.run(str(study.id))

    # Assert
    result = _result(study)
    assert result.status == "FAILED"
    assert "400" in result.error
    assert result.model_seg_series_uid == ""
    assert f"{study.id}/study_{study.id}.nii.gz" in stored


def test_a_second_run_reuses_the_row_and_replaces_the_previous_seg(pipeline, study):
    # Arrange
    from segmentation.models import SegmentationResult

    tasks, orthanc, _ = pipeline
    tasks.run(str(study.id))
    first = _result(study)

    # Act
    tasks.run(str(study.id))

    # Assert
    second = _result(study)
    assert SegmentationResult.objects.filter(study=study).count() == 1
    assert second.pk == first.pk
    assert second.status == "COMPLETED"
    assert orthanc.deleted_series == [first.model_seg_series_uid]
    assert second.model_seg_series_uid == orthanc.uploaded[-1].SeriesInstanceUID


@pytest.mark.parametrize("verified", ["APPROVED", "CORRECTED"])
def test_a_verified_mask_is_never_replaced(pipeline, study, verified):
    # Arrange
    from segmentation.models import SegmentationResult

    tasks, orthanc, stored = pipeline
    SegmentationResult.objects.create(
        study=study, status=verified, generated_path="1/mask.nii.gz", model_seg_series_uid="1.2"
    )

    # Act
    tasks.run(str(study.id))

    # Assert
    result = _result(study)
    assert (result.status, result.generated_path) == (verified, "1/mask.nii.gz")
    assert orthanc.uploaded == orthanc.deleted_series == []
    assert stored == {}


def test_a_deleted_study_is_skipped(pipeline, study):
    tasks, orthanc, stored = pipeline
    study_id = study.id
    study.delete()

    tasks.run(str(study_id))

    assert orthanc.uploaded == []
    assert stored == {}


def test_a_study_deleted_during_the_run_gets_nothing_stored(pipeline, study, monkeypatch):
    # Arrange
    tasks, orthanc, stored = pipeline
    predict = FakeModel.predict

    def predict_then_delete(self, *args):
        prediction = predict(self, *args)
        study.delete()
        return prediction

    monkeypatch.setattr(FakeModel, "predict", predict_then_delete)

    # Act
    tasks.run(str(study.id))

    # Assert
    assert orthanc.uploaded == []
    assert stored == {}


def test_approval_saves_the_uids_of_the_approved_seg(pipeline, study, monkeypatch):
    # Arrange
    from segmentation.models import SegmentationResult

    tasks, orthanc, stored = pipeline
    tasks.run(str(study.id))
    result = _result(study)
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


def _correct_in_viewer(pipeline, study, tmp_path, on_series=None):
    """The model's mask with one more voxel, sent as a SEG to Orthanc and approved as CORRECTED.

    ``on_series`` draws the SEG on another series of the study, as today's viewer does on `post`.
    Returns the corrected mask the SEG was made from.
    """
    import nibabel as nib
    import numpy as np
    import pydicom
    from segmentation.models import StatusChoices

    from workers.segmentation.conversion import convert_nifti_to_dicom_seg

    tasks, orthanc, stored = pipeline
    tasks.run(str(study.id))
    result = _result(study)
    model_path = tmp_path / "model.nii.gz"
    model_path.write_bytes(stored[result.generated_path])
    model = nib.load(model_path)
    corrected = np.asarray(model.dataobj).copy()
    corrected[4, 2, 3] = 1
    nib.save(nib.Nifti1Image(corrected, model.affine), tmp_path / "corrected.nii.gz")

    study_dir = tmp_path / "viewer"
    orthanc.download_study(study.orthanc_path, study_dir)
    if on_series:
        seg_path = _seg_on_series(tmp_path, study_dir, series_number=on_series)
    else:
        seg_path = convert_nifti_to_dicom_seg(
            study_dir, tmp_path / "corrected.nii.gz", tmp_path / "corrected.dcm"
        ).path
    seg = pydicom.dcmread(seg_path)
    orthanc.uploaded.append(seg)
    result.status = StatusChoices.CORRECTED
    result.approved_seg_series_uid = seg.SeriesInstanceUID
    result.approved_seg_sop_uid = seg.SOPInstanceUID
    result.save()
    return corrected


def test_a_corrected_seg_becomes_the_accepted_mask_with_its_measurements(pipeline, study, tmp_path):
    # Arrange
    import nibabel as nib
    import numpy as np

    from workers.segmentation.measurements import measure

    tasks, orthanc, stored = pipeline
    corrected = _correct_in_viewer(pipeline, study, tmp_path)
    model_key = _result(study).generated_path

    # Act
    tasks.correction_from_dicom_seg(_result(study).id)

    # Assert: the corrected voxels on the model's grid; the model's own mask stays as it was
    result = _result(study)
    assert result.accepted_path == f"{study.id}/study_{study.id}_corrected.nii.gz"
    (tmp_path / "accepted.nii.gz").write_bytes(stored[result.accepted_path])
    accepted = nib.load(tmp_path / "accepted.nii.gz")
    assert np.array_equal(np.asarray(accepted.dataobj), corrected)
    assert result.measurements == measure(corrected, accepted.affine)
    assert (result.status, result.error) == ("CORRECTED", "")
    assert result.generated_path == model_key and model_key in stored


def test_a_corrected_seg_drawn_on_another_phase_is_kept_as_an_error(pipeline, study, tmp_path):
    # Arrange
    from workers.segmentation.conversion import GeometryError

    tasks, orthanc, stored = pipeline
    _correct_in_viewer(pipeline, study, tmp_path, on_series=2)
    before = _result(study).measurements

    # Act
    with pytest.raises(GeometryError):
        tasks.correction_from_dicom_seg(_result(study).id)

    # Assert: the approval stands, nothing is stored and the reason can be shown
    result = _result(study)
    assert result.status == "CORRECTED"
    assert result.error.startswith("GeometryError")
    assert result.accepted_path is None
    assert result.measurements == before
    assert f"{study.id}/study_{study.id}_corrected.nii.gz" not in stored


def test_a_mask_without_a_corrected_seg_is_not_converted(pipeline, study):
    # Arrange: the model's mask, not approved
    tasks, orthanc, stored = pipeline
    tasks.run(str(study.id))
    files = dict(stored)

    # Act
    tasks.correction_from_dicom_seg(_result(study).id)

    # Assert
    assert _result(study).accepted_path is None
    assert stored == files


# --- uncertainty ---


def _probability_map(tmp_path, values):
    import nibabel as nib
    import numpy as np

    path = tmp_path / "prob.nii.gz"
    nib.save(nib.Nifti1Image(np.asarray(values, dtype=np.float32), np.eye(4)), path)
    return path


def test_uncertainty_is_the_mean_entropy_inside_the_lesion(tmp_path):
    from workers.segmentation.tasks import _calculate_uncertainty

    # p = 0.5 has an entropy of exactly 1 bit; voxels at p <= 0.05 are background and skipped
    values = [[[0.5, 0.5], [0.01, 0.0]]]

    assert _calculate_uncertainty(_probability_map(tmp_path, values)) == pytest.approx(1.0)


def test_uncertainty_of_an_empty_probability_map_is_unknown(tmp_path):
    from workers.segmentation.tasks import _calculate_uncertainty

    assert _calculate_uncertainty(_probability_map(tmp_path, [[[0.0, 0.0], [0.0, 0.0]]])) is None


def test_uncertainty_of_an_unreadable_file_is_unknown(tmp_path):
    from workers.segmentation.tasks import _calculate_uncertainty

    path = tmp_path / "prob.nii.gz"
    path.write_bytes(b"not a nifti")

    assert _calculate_uncertainty(path) is None


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
