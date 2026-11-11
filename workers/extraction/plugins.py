from importlib import import_module

from .errors import UnknownComponentError


def load_class(
    targets: dict[str, str],
    name: str,
    kind: str,
    package: str,
    *,
    setting: str,
    extra: tuple[str, ...] = (),
) -> type:
    """Class registered under ``name`` in ``targets`` (``"module:Class"``), imported on demand.

    ``kind`` and ``setting`` only serve the error message: what is being chosen and which
    environment variable / CLI flag chose it.
    """
    try:
        target = targets[name]
    except KeyError:
        available = ", ".join([*extra, *targets])
        raise UnknownComponentError(
            f"Unknown {kind} {name!r} (set by {setting}); available: {available}."
        ) from None
    module_name, class_name = target.split(":")
    return getattr(import_module(module_name, package), class_name)
