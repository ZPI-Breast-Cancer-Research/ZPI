import re

from ..normalize import fold, quote_similarity
from ..schema import (
    Brzeg,
    Echogenicznosc,
    EkstrakcjaBadania,
    Ksztalt,
    Modalnosc,
    Obserwacja,
    Strona,
)

QUOTE_MIN_SIMILARITY = 0.85
VERBATIM_MIN_SIMILARITY = 0.9
USG_ONLY_FIELDS = ("echogenicznosc", "jednorodnosc", "glebokosc")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_WORD = re.compile(r"[^\W\d_]+")

STEMS = {
    Ksztalt.OKRAGLY: ("okrag",),
    Ksztalt.OWALNY: ("owal",),
    Ksztalt.NIEREGULARNY: ("nieregular",),
    Brzeg.OBWIEDZIONY: ("obwiedz", "ostro odgranicz"),
    Brzeg.NIEOSTRY: ("nieostr",),
    Brzeg.ZATARTY: ("zatar",),
    Brzeg.MIKROPLATOWATY: ("mikroplat",),
    Brzeg.KATOWY: ("katow",),
    Brzeg.SPIKULARNY: ("spikul", "promienist"),
    Echogenicznosc.BEZECHOWA: ("bezech",),
    Echogenicznosc.HIPOECHOGENICZNA: ("hipoech", "hypoech", "obnizonej echogenicz"),
    Echogenicznosc.IZOECHOGENICZNA: ("izoech", "isoech", "normoech"),
    Echogenicznosc.HIPERECHOGENICZNA: ("hiperech", "hyperech"),
    Echogenicznosc.ZLOZONA: ("zlozon", "torbielowatolit", "litotorbiel"),
}


def check_extraction(data: EkstrakcjaBadania, text: str) -> list[str]:
    warnings = []
    haystack = fold(text)

    for name in ("lewa", "prawa"):
        piers = getattr(data.piersi, name)
        warnings += _verbatim(f"pierś {name}: budowa", piers.budowa, haystack)
        warnings += _verbatim(f"pierś {name}: skora.stan", piers.skora.stan, haystack)

    for zmiana in data.zmiany:
        for i, obs in enumerate(zmiana.obserwacje, start=1):
            warnings += _check_observation(f"zmiana {zmiana.id}, obserwacja {i}", obs, haystack)
    for i, wezel in enumerate(data.wezly, start=1):
        where = f"węzeł {i}"
        if quote_similarity(wezel.cytat, haystack) < QUOTE_MIN_SIMILARITY:
            warnings.append(f"{where}: cytatu nie znaleziono w opisie")
        warnings += _verbatim(f"{where}: uwagi", wezel.uwagi, haystack)
        if wezel.wymiary:
            warnings += _numbers(where, "wymiary", wezel.wymiary.wartosci, wezel.cytat)

    warnings += _verbatim("wniosek: tekst", data.wniosek.tekst, haystack)
    warnings += _verbatim("wniosek: zalecenie", data.wniosek.zalecenie, haystack)

    ids = [z.id for z in data.zmiany]
    if len(set(ids)) != len(ids):
        warnings.append("powtórzone numery zmian (id)")
    for zmiana in data.zmiany:
        if not zmiana.obserwacje:
            warnings.append(f"zmiana {zmiana.id}: brak obserwacji")
        if len(zmiana.obserwacje) > 1 and zmiana.polaczenie_obserwacji is None:
            warnings.append(f"zmiana {zmiana.id}: kilka obserwacji bez polaczenie_obserwacji")
        if len(zmiana.obserwacje) <= 1 and zmiana.polaczenie_obserwacji is not None:
            warnings.append(f"zmiana {zmiana.id}: polaczenie_obserwacji przy jednej obserwacji")
        for strona in _sides(zmiana.strona):
            if getattr(data.piersi, strona).zmiany_ogniskowe is False:
                warnings.append(
                    f"zmiana {zmiana.id}: pierś {strona} ma zmiany_ogniskowe = false"
                )
    return warnings


def _check_observation(where: str, obs: Obserwacja, haystack: str) -> list[str]:
    where = f"{where} ({obs.modalnosc})"
    warnings = []
    if quote_similarity(obs.cytat, haystack) < QUOTE_MIN_SIMILARITY:
        warnings.append(f"{where}: cytatu nie znaleziono w opisie")
    if obs.modalnosc == Modalnosc.MAMMOGRAFIA:
        warnings += [
            f"{where}: pole {name} dotyczy tylko USG"
            for name in USG_ONLY_FIELDS
            if getattr(obs, name) is not None
        ]
    warnings += _verbatim(f"{where}: typ", obs.typ, haystack)
    for lokalizacja in obs.lokalizacje:
        warnings += _verbatim(f"{where}: lokalizacja", lokalizacja, haystack)

    if obs.wymiary:
        warnings += _numbers(where, "wymiary", obs.wymiary.wartosci, obs.cytat)
    for name in ("odleglosc_od_brodawki", "glebokosc"):
        miara = getattr(obs, name)
        if miara:
            warnings += _numbers(where, name, [miara.wartosc], obs.cytat)
    if obs.godzina:
        warnings += _numbers(where, "godzina", _numbers_in(obs.godzina), obs.cytat)

    quote = fold(obs.cytat)
    for name in ("ksztalt", "brzeg", "echogenicznosc"):
        value = getattr(obs, name)
        if value is not None and not any(stem in quote for stem in STEMS[value]):
            warnings.append(f"{where}: {name} = {value} nie wynika z cytatu")
    return warnings


def _verbatim(where: str, value: str | None, haystack: str) -> list[str]:
    if not value:
        return []
    missing = [
        word
        for word in _WORD.findall(value)
        if len(word) >= 4 and quote_similarity(word, haystack) < VERBATIM_MIN_SIMILARITY
    ]
    if missing:
        return [f"{where} „{value}”: w opisie brak słów {', '.join(missing)}"]
    return []


def _numbers(where: str, name: str, values: list[float], quote: str) -> list[str]:
    present = set(_numbers_in(quote))
    return [
        f"{where}: {name} {value:g} nie występuje w cytacie"
        for value in values
        if value not in present
    ]


def _numbers_in(text: str) -> list[float]:
    return [float(n.replace(",", ".")) for n in _NUMBER.findall(text)]


def _sides(strona: Strona) -> tuple[str, ...]:
    return ("lewa", "prawa") if strona == Strona.OBUSTRONNIE else (strona.value,)
