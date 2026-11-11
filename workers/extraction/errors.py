"""All exceptions of the extraction module; ``ExtractionError`` catches any of them."""


class ExtractionError(Exception):
    pass


class ConfigError(ExtractionError):
    """Invalid setting: a malformed environment variable or an unknown component name."""


class InputError(ExtractionError):
    """The input path does not exist or is not a report (text file or image)."""


class EvaluationDataError(ExtractionError):
    """A gold or prediction file cannot be read as the expected data."""


class LLMError(ExtractionError):
    pass


class LLMConnectionError(LLMError):
    pass


class HostNotAllowedError(LLMError):
    pass


class OcrError(ExtractionError):
    pass


class OrientationError(ExtractionError):
    pass


class ParseError(ExtractionError):
    """The LLM answer is not valid JSON or does not match the schema."""
