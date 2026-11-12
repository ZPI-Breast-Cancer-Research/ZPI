"""Layout-only clean-up of report text before the LLM: never changes words or numbers."""

import re
import unicodedata

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACES = re.compile(r"[ \t ]+")
_HYPHENATED_BREAK = re.compile(r"(?<=[a-ząćęłńóśźż])-\n(?=[a-ząćęłńóśźż])")
_MANY_BLANK_LINES = re.compile(r"\n{3,}")
_REPORT_START = re.compile(r"opis badania\s*:?", re.IGNORECASE)
_REPORT_END = re.compile(
    r"(?im)^[ \t]*(?:\S*/a|Wykonał/a|Wykonal/a)[ \t]*:"
    r"|^[ \t]*Opis[ \t]*:[ \t]*$"
)


def normalize_text(text: str) -> str:
    r"""Clean the layout of a report text (usually OCR output) before it goes to the LLM.


    Words and numbers are never changed.

    EXAMPLE:
        Input (OCR output)::

            SZPITAL XYZ
            Pacjent:   Jan    K.


            Opis badania:
            W USG pier-
            si prawej zmiana hipoecho-
            geniczna   12 mm, wymiary 2-
            3 cm.
            Wykonat/a: dr N.
            Opis:

        Output::

            Opis badania:
            W USG piersi prawej zmiana hipoechogeniczna 12 mm, wymiary 2-
            3 cm.

        The header (hospital, patient) and the footer (doctor, empty "Opis:") are cut off,
        "Wykonat/a:" is recognised although OCR misread "Wykonał", "pier-/si" and
        "hipoecho-/geniczna" are joined, extra spaces collapse, and the number range "2-/3"
        keeps its line break because digits are never joined.
    """
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
