from importlib import import_module


def load_class(
    targets: dict[str, str], name: str, kind: str, package: str, *, extra: tuple[str, ...] = ()
) -> type:
    try:
        target = targets[name]
    except KeyError:
        available = ", ".join([*extra, *targets])
        raise ValueError(f"Unknown {kind} {name!r}; available: {available}") from None
    module_name, class_name = target.split(":")
    return getattr(import_module(module_name, package), class_name)
