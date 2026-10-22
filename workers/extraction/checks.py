import re
import unicodedata
from difflib import SequenceMatcher

from .schema import EkstrakcjaBadania

QUOTE_MIN_SIMILARITY = 0.85


def check_extraction(data: EkstrakcjaBadania, text: str) -> list[str]:
    warnings = []
    haystack = _fold(text)

    for zmiana in data.zmiany:
        if quote_similarity(zmiana.cytat, haystack) < QUOTE_MIN_SIMILARITY:
            warnings.append(f"zmiana {zmiana.nr}: cytatu nie znaleziono w opisie")
    for i, wezel in enumerate(data.wezly_chlonne, start=1):
        if quote_similarity(wezel.cytat, haystack) < QUOTE_MIN_SIMILARITY:
            warnings.append(f"węzeł {i}: cytatu nie znaleziono w opisie")

    numbers = {z.nr for z in data.zmiany}
    if len(numbers) != len(data.zmiany):
        warnings.append("powtórzone numery zmian (nr)")
    for zmiana in data.zmiany:
        link = zmiana.powiazana_ze_zmiana
        if link is not None and (link not in numbers or link == zmiana.nr):
            warnings.append(f"zmiana {zmiana.nr}: powiazana_ze_zmiana={link} wskazuje złą zmianę")
    return warnings


def quote_similarity(quote: str, folded_text: str) -> float:
    needle = _fold(quote)
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


def _fold(text: str) -> str:
    text = text.lower().replace("ł", "l")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip()
