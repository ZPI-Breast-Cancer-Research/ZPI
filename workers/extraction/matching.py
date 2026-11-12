"""Fuzzy text matching that tolerates OCR noise, case and Polish diacritics."""

import re
import unicodedata
from difflib import SequenceMatcher


def fold(text: str) -> str:
    """Lower case, no diacritics, no hyphens, single spaces: ``"Hipo-echogeniczna  Ł"`` ->
    ``"hipoechogeniczna l"``."""
    text = text.lower().replace("ł", "l").replace("-", "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip()


def quote_similarity(quote: str, folded_text: str) -> float:
    """How well ``quote`` occurs in ``folded_text`` (already passed through ``fold``), 0..1.

    1.0 for an exact substring, otherwise the best ``SequenceMatcher`` ratio of a window of the
    quote's length slid over the text in steps of a tenth of that length (approximate).

    EXAMPLE:
        text = fold("W USG zmiana hipoechogeniczna 12 mm.")

        quote_similarity("Zmiana HIPOECHOGENICZNA", text)  -> 1.0   (case ignored)
        quote_similarity("zmiana hipoechogenlczna", text)  -> 0.96  (OCR typo "l")
        quote_similarity("torbiel prosta", text)           -> 0.21  (not in the text)
    """
    needle = fold(quote)
    if not needle:
        return 0.0
    if needle in folded_text:
        return 1.0
    size = len(needle)
    step = max(1, size // 10)
    best = 0.0
    for start in range(0, max(1, len(folded_text) - size + 1), step):
        window = folded_text[start : start + size]
        best = max(best, SequenceMatcher(None, needle, window, autojunk=False).ratio())
    return best


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, fold(a), fold(b), autojunk=False).ratio()
