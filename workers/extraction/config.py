import os
from dataclasses import dataclass
from typing import TypeVar

from .errors import InvalidSettingValueError

N = TypeVar("N", int, float)

DEFAULT_ALLOWED_HOSTS = ("localhost", "127.0.0.1", "host.docker.internal")
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise InvalidSettingValueError(
        f"Environment variable {name}={raw!r} is not a true/false value; "
        f"use one of: {', '.join(sorted(TRUE_VALUES))} / {', '.join(sorted(FALSE_VALUES))}."
    )


def _env_number(name: str, default: N, kind: type[N]) -> N:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return kind(raw)
    except ValueError:
        expected = "a whole number, e.g. 1" if kind is int else "a number, e.g. 300"
        raise InvalidSettingValueError(
            f"Environment variable {name}={raw!r} is not valid; expected {expected}."
        ) from None


@dataclass
class Settings:
    ocr_engine: str = "paddle"
    ocr_lang: str = "pl"
    ocr_orientation: str = "paddle"

    llm_provider: str = "local_http"
    llm_base_url: str = "http://localhost:1234/v1"
    llm_model: str = ""
    llm_timeout: float = 300.0
    llm_allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS
    llm_structured_output: bool = True
    few_shot_examples: int = 1

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            ocr_engine=os.environ.get("OCR_ENGINE", defaults.ocr_engine),
            ocr_lang=os.environ.get("OCR_LANG", defaults.ocr_lang),
            ocr_orientation=os.environ.get("OCR_ORIENTATION", defaults.ocr_orientation),
            llm_provider=os.environ.get("LLM_PROVIDER", defaults.llm_provider),
            llm_base_url=os.environ.get("LLM_BASE_URL", defaults.llm_base_url),
            llm_model=os.environ.get("LLM_MODEL", defaults.llm_model),
            llm_timeout=_env_number("LLM_TIMEOUT", defaults.llm_timeout, float),
            llm_allowed_hosts=_env_list("LLM_ALLOWED_HOSTS", defaults.llm_allowed_hosts),
            llm_structured_output=_env_bool(
                "LLM_STRUCTURED_OUTPUT", defaults.llm_structured_output
            ),
            few_shot_examples=_env_number("EXTRACTION_FEW_SHOT", defaults.few_shot_examples, int),
        )
