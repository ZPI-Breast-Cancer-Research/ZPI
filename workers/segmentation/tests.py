import os
from pathlib import Path

import pytest

from workers.segmentation.channels import CHANNELS, channel_names, channel_suffix

# A real prediction needs model weights, which are not in the repository.
MODEL_DIR = os.environ.get("SEGMENTATION_TEST_MODEL_DIR")
INPUTS = os.environ.get("SEGMENTATION_TEST_INPUTS")  # channel files, separated by os.pathsep


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


@pytest.mark.skipif(
    not (MODEL_DIR and INPUTS),
    reason="set SEGMENTATION_TEST_MODEL_DIR and SEGMENTATION_TEST_INPUTS to run a real prediction",
)
def test_prediction_has_the_geometry_of_the_input(tmp_path):
    import numpy as np
    import SimpleITK as sitk

    from workers.segmentation.models.registry import get_segmentation_model

    channels = [Path(path) for path in INPUTS.split(os.pathsep)]
    model = get_segmentation_model(Path(MODEL_DIR))

    result = model.predict(channels, tmp_path, "case")

    reference = sitk.ReadImage(str(channels[0]))
    for path in (result.label_path, result.probabilities_path):
        output = sitk.ReadImage(str(path))
        assert output.GetSize() == reference.GetSize()
        assert np.allclose(output.GetSpacing(), reference.GetSpacing())
        assert np.allclose(output.GetOrigin(), reference.GetOrigin(), atol=1e-3)
        assert np.allclose(output.GetDirection(), reference.GetDirection())
    labels = sitk.GetArrayFromImage(sitk.ReadImage(str(result.label_path)))
    probabilities = sitk.GetArrayFromImage(sitk.ReadImage(str(result.probabilities_path)))
    assert set(np.unique(labels)) <= {0, 1}
    assert probabilities.min() >= 0 and probabilities.max() <= 1
