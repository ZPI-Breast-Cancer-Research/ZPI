import re
import unicodedata

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACES = re.compile(r"[ \t ]+")
_HYPHENATED_BREAK = re.compile(r"(?<=[a-ząćęłńóśźż])-\n(?=[a-ząćęłńóśźż])")
_MANY_BLANK_LINES = re.compile(r"\n{3,}")
_REPORT_START = re.compile(r"opis badania\s*:?", re.IGNORECASE)
# Form footer below the report: "Wykonał/a:" (OCR often mangles the word, keeps "/a:")
# and the empty "Opis:" field.
_REPORT_END = re.compile(r"\S*/a\s*:|\bopis\s*:", re.IGNORECASE)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    text = "\n".join(_SPACES.sub(" ", line).strip() for line in text.split("\n"))
    text = _HYPHENATED_BREAK.sub("", text)
    text = _MANY_BLANK_LINES.sub("\n\n", text)
    start = _REPORT_START.search(text)
    body_from = 0
    if start:
        text = text[start.start() :]
        body_from = start.end() - start.start()
    end = _REPORT_END.search(text, body_from)
    if end:
        text = text[: end.start()]
    return text.strip()
