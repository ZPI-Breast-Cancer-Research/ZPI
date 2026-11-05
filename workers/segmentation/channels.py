# Order defines nnU-Net channel indices (_0000, _0001, ...).
# Changing it invalidates trained models.
CHANNELS = ("pre", "post1", "post2")


def channel_suffix(role: str) -> str:
    return f"{CHANNELS.index(role):04d}"


def channel_names() -> dict[str, str]:
    return {str(i): role for i, role in enumerate(CHANNELS)}
