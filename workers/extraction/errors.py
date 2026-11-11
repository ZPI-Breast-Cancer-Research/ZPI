"""All exceptions of the extraction module; ``ExtractionError`` catches any of them."""


class ExtractionError(Exception):
    """Base of every expected error of the module; the CLI prints it as a one-line message."""


class ConfigError(ExtractionError):
    """Malformed environment variable or unknown component name (e.g. ``--ocr bogus``)."""


class UnsupportedFileTypeError(ExtractionError):
    """Input file is neither a text file nor an image."""


class EvaluationDataError(ExtractionError):
    """Gold or prediction file cannot be read as the expected data."""


class LLMError(ExtractionError):
    """LLM server failed or answered something unusable (HTTP error, non-JSON, no model)."""


class LLMConnectionError(LLMError):
    """LLM server cannot be reached or did not answer within ``LLM_TIMEOUT``."""


class HostNotAllowedError(LLMError):
    """LLM URL is outside ``LLM_ALLOWED_HOSTS``; raised before any report text is sent."""


class OcrError(ExtractionError):
    """OCR engine cannot be used, e.g. PaddleOCR is not installed."""


class OrientationError(ExtractionError):
    """Orientation detector cannot be used or returned no angle for a page."""


class ParseError(ExtractionError):
    """LLM answer is not valid JSON or does not match the schema."""
