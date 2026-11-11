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


def _write_mr_series(directory, study_uid, frame_uid, number, acquisition_time):
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
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
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


def test_dicom_seg_marks_the_same_source_voxel_as_the_nifti_mask(tmp_path):
    # Arrange
    import highdicom as hd
    import nibabel as nib
    import numpy as np
    from pydicom.uid import generate_uid

    from workers.segmentation.conversion import Status, convert_nifti_to_dicom_seg, convert_study

    study_dir = tmp_path / "dicom"
    study_dir.mkdir()
    study_uid, frame_uid = generate_uid(), generate_uid()
    pre_sops = _write_mr_series(study_dir, study_uid, frame_uid, 1, "120000")
    _write_mr_series(study_dir, study_uid, frame_uid, 2, "120100")
    _write_mr_series(study_dir, study_uid, frame_uid, 3, "120200")

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
    seg_path = convert_nifti_to_dicom_seg(study_dir, mask_path, tmp_path / "seg.dcm")

    # Assert
    seg = hd.seg.segread(seg_path)
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
