import os
from dataclasses import dataclass, field

DEFAULT_ALLOWED_HOSTS = ("localhost", "127.0.0.1", "host.docker.internal")


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    ocr_engine: str = "paddle"
    ocr_lang: str = "pl"
    ocr_orientation: str = "paddle"

    llm_provider: str = "local_http"
    llm_base_url: str = "http://localhost:1234/v1"
    llm_model: str = ""
    llm_timeout: float = 300.0
    llm_allowed_hosts: tuple[str, ...] = field(default=DEFAULT_ALLOWED_HOSTS)
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
            llm_timeout=float(os.environ.get("LLM_TIMEOUT", defaults.llm_timeout)),
            llm_allowed_hosts=_env_list("LLM_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS),
            llm_structured_output=_env_bool(
                "LLM_STRUCTURED_OUTPUT", defaults.llm_structured_output
            ),
            few_shot_examples=int(
                os.environ.get("EXTRACTION_FEW_SHOT", defaults.few_shot_examples)
            ),
        )
