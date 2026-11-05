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
