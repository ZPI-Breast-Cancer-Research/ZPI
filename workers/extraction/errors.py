"""All exceptions of the extraction module; ``ExtractionError`` catches any of them."""


class ExtractionError(Exception):
    pass


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
