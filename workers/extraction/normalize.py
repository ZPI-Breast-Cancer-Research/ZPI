import re
import unicodedata

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACES = re.compile(r"[ \t ]+")
_HYPHENATED_BREAK = re.compile(r"(?<=[a-ząćęłńóśźż])-\n(?=[a-ząćęłńóśźż])")
_MANY_BLANK_LINES = re.compile(r"\n{3,}")
_REPORT_START = re.compile(r"opis badania\s*:?", re.IGNORECASE)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    text = "\n".join(_SPACES.sub(" ", line).strip() for line in text.split("\n"))
    text = _HYPHENATED_BREAK.sub("-", text)
    text = _MANY_BLANK_LINES.sub("\n\n", text)
    start = _REPORT_START.search(text)
    if start:
        text = text[start.start() :]
    return text.strip()
