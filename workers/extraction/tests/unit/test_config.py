import pytest

from workers.extraction.config import DEFAULT_ALLOWED_HOSTS, Settings
from workers.extraction.errors import InvalidSettingValueError

ENV_VARS = (
    "OCR_ENGINE",
    "OCR_LANG",
    "OCR_ORIENTATION",
    "LLM_PROVIDER",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_TIMEOUT",
    "LLM_ALLOWED_HOSTS",
    "LLM_STRUCTURED_OUTPUT",
    "EXTRACTION_FEW_SHOT",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_without_environment():
    # Act
    settings = Settings.from_env()

    # Assert
    assert settings == Settings()
    assert settings.llm_allowed_hosts == DEFAULT_ALLOWED_HOSTS
    assert settings.llm_structured_output is True
    assert settings.few_shot_examples == 1


def test_environment_overrides_defaults(monkeypatch):
    # Arrange
    monkeypatch.setenv("OCR_ENGINE", "other")
    monkeypatch.setenv("LLM_MODEL", "bielik")
    monkeypatch.setenv("LLM_TIMEOUT", "12.5")
    monkeypatch.setenv("EXTRACTION_FEW_SHOT", "0")

    # Act
    settings = Settings.from_env()

    # Assert
    assert settings.ocr_engine == "other"
    assert settings.llm_model == "bielik"
    assert settings.llm_timeout == 12.5
    assert settings.few_shot_examples == 0


def test_allowed_hosts_are_a_comma_separated_list(monkeypatch):
    # Arrange
    monkeypatch.setenv("LLM_ALLOWED_HOSTS", " localhost, llm-server ,,")

    # Act
    settings = Settings.from_env()

    # Assert
    assert settings.llm_allowed_hosts == ("localhost", "llm-server")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("1", True),
        ("Yes", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("off", False),
    ],
)
def test_structured_output_reads_true_false_values(monkeypatch, raw, expected):
    # Arrange
    monkeypatch.setenv("LLM_STRUCTURED_OUTPUT", raw)

    # Act
    settings = Settings.from_env()

    # Assert
    assert settings.llm_structured_output is expected


@pytest.mark.parametrize(
    ("name", "raw"),
    [("LLM_STRUCTURED_OUTPUT", "maybe"), ("LLM_TIMEOUT", "abc"), ("EXTRACTION_FEW_SHOT", "1.5")],
)
def test_invalid_value_names_the_variable(monkeypatch, name, raw):
    # Arrange
    monkeypatch.setenv(name, raw)

    # Act / Assert
    with pytest.raises(InvalidSettingValueError, match=name):
        Settings.from_env()
