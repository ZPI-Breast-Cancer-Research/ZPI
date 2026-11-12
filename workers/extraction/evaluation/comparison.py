"""Comparison of one gold document with one prediction, field by field."""

import math
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from ..matching import fold, quote_similarity, text_similarity
from ..schema import EkstrakcjaBadania, Obserwacja, Piersi, Wezel, Wniosek, Wymiary, Zmiana
from .report import Report

TEXT_MIN_SIMILARITY = 0.9
MATCH_MIN_SIMILARITY = 0.6
PIERS_FLAGS = ("obrzek", "zwapnienia", "mikrozwapnienia", "zmiany_ogniskowe")
OBS_EXACT = ("godzina", "ksztalt", "brzeg", "echogenicznosc", "jednorodnosc", "naciek_skory")

T = TypeVar("T")


class Comparison:
    """Compares gold documents with predictions and collects the counts in one ``Report``.

    One instance per evaluation run; each method compares one part of a document and walks
    down the schema (document -> lesion -> observation -> dimensions).
    """

    def __init__(self) -> None:
        self.report = Report()

    def document(self, gold: EkstrakcjaBadania, pred: EkstrakcjaBadania) -> None:
        """Score one document: single-valued parts directly, lesions and nodes after pairing."""
        # Order does not matter, and an empty list counts as no answer.
        self._compare_field(
            "modalnosci", set(gold.modalnosci) or None, set(pred.modalnosci) or None
        )
        self._breasts(gold.piersi, pred.piersi)
        self._conclusion(gold.wniosek, pred.wniosek)

        for g_lesion, p_lesion in self._match("zmiany", gold.zmiany, pred.zmiany, _lesion_sim):
            self._lesion(g_lesion, p_lesion)
        for g_node, p_node in self._match("wezly", gold.wezly, pred.wezly, _node_sim):
            self._node(g_node, p_node)

    def _breasts(self, gold: Piersi, pred: Piersi) -> None:
        # Both sides are scored under the same field names, so each row covers left and right.
        for side in ("lewa", "prawa"):
            g, p = getattr(gold, side), getattr(pred, side)
            self._compare_field("piersi.budowa", g.budowa, p.budowa, _same_text)
            for name in PIERS_FLAGS:
                self._compare_field(f"piersi.{name}", getattr(g, name), getattr(p, name))
            self._compare_field("piersi.skora.stan", g.skora.stan, p.skora.stan, _same_text)
            self._compare_field("piersi.skora.naciek", g.skora.naciek, p.skora.naciek)

    def _conclusion(self, gold: Wniosek, pred: Wniosek) -> None:
        self._compare_field("wniosek.birads", gold.birads, pred.birads)
        self._compare_field("wniosek.tekst", gold.tekst, pred.tekst, _same_text)
        self._compare_field("wniosek.zalecenie", gold.zalecenie, pred.zalecenie, _same_text)

    def _lesion(self, gold: Zmiana, pred: Zmiana) -> None:
        self._compare_field("zmiana.strona", gold.strona, pred.strona)
        self._compare_field("zmiana.birads", gold.birads, pred.birads)
        self._compare_field(
            "zmiana.polaczenie_obserwacji.pewne",
            gold.polaczenie_obserwacji and gold.polaczenie_obserwacji.pewne,
            pred.polaczenie_obserwacji and pred.polaczenie_obserwacji.pewne,
        )
        for g_obs, p_obs in self._match(
            "obserwacje", gold.obserwacje, pred.obserwacje, _observation_sim
        ):
            self._observation(g_obs, p_obs)

    def _observation(self, gold: Obserwacja, pred: Obserwacja) -> None:
        prefix = f"obserwacja.{gold.modalnosc}"
        self._compare_field(
            f"{prefix}.lokalizacje",
            {fold(x) for x in gold.lokalizacje} or None,
            {fold(x) for x in pred.lokalizacje} or None,
        )
        self._compare_field(f"{prefix}.typ", gold.typ, pred.typ, _same_text)
        for name in OBS_EXACT:
            self._compare_field(f"{prefix}.{name}", getattr(gold, name), getattr(pred, name))
        for name in ("odleglosc_od_brodawki", "glebokosc"):
            g, p = getattr(gold, name), getattr(pred, name)
            self._compare_field(f"{prefix}.{name}", g and g.mm(), p and p.mm(), math.isclose)
        self._dimensions(prefix, gold.wymiary, pred.wymiary)

    def _node(self, gold: Wezel, pred: Wezel) -> None:
        self._compare_field("wezel.strona", gold.strona, pred.strona)
        self._compare_field("wezel.okolica", gold.okolica, pred.okolica, _same_text)
        self._compare_field("wezel.liczba", gold.liczba, pred.liczba)
        self._compare_field("wezel.patologiczne", gold.patologiczne, pred.patologiczne)
        self._compare_field("wezel.uwagi", gold.uwagi, pred.uwagi, _same_text)
        self._dimensions("wezel", gold.wymiary, pred.wymiary)

    def _dimensions(self, prefix: str, gold: Wymiary | None, pred: Wymiary | None) -> None:
        for name in ("wartosci", "jednostka", "kwalifikator"):
            self._compare_field(f"{prefix}.wymiary.{name}", _attr(gold, name), _attr(pred, name))
        self._compare_field(
            f"{prefix}.wymiary.max_mm",
            gold and gold.max_mm(),
            pred and pred.max_mm(),
            math.isclose,
        )

    def _compare_field(
        self,
        name: str,
        gold: Any,
        pred: Any,
        same: Callable[[Any, Any], bool] = lambda a, b: a == b,
    ) -> None:
        """Count one field of one document: hand-checked ``gold`` value vs model ``pred`` value.

        gold    pred    result
        None    None    not counted (nothing to find, nothing found)
        value   None    missed    - the model left out a value that is in the report
        None    value   spurious  - the model filled in a value that is not in the report
        value   value   correct   - if ``same(gold, pred)`` (``==`` by default, ``_same_text``
                                    for verbatim text, ``math.isclose`` for sizes in mm)
        value   value   wrong     - otherwise

        EXAMPLE:
            self._compare_field("wniosek.birads", "4a", "4a")  -> correct
            self._compare_field("wniosek.birads", "4a", "3")   -> wrong
            self._compare_field("wniosek.birads", "4a", None)  -> missed
            self._compare_field("piersi.obrzek", None, True)   -> spurious
        """
        if gold is None and pred is None:
            return
        score = self.report.field_score(name)
        if gold is None:
            score.spurious += 1
        elif pred is None:
            score.missed += 1
        elif same(gold, pred):
            score.correct += 1
        else:
            score.wrong += 1

    def _match(
        self,
        entity: str,
        gold: Sequence[T],
        pred: Sequence[T],
        similarity: Callable[[T, T], float],
    ) -> list[tuple[T, T]]:
        """Pair gold and predicted items greedily, most similar first; count the pairs."""
        candidates = sorted(
            ((similarity(g, p), i, j) for i, g in enumerate(gold) for j, p in enumerate(pred)),
            reverse=True,
        )
        used_gold: set[int] = set()
        used_pred: set[int] = set()
        pairs = []
        for score, i, j in candidates:
            if score < MATCH_MIN_SIMILARITY:
                break
            if i not in used_gold and j not in used_pred:
                used_gold.add(i)
                used_pred.add(j)
                pairs.append((gold[i], pred[j]))

        counts = self.report.entity_score(entity)
        counts.gold += len(gold)
        counts.predicted += len(pred)
        counts.matched += len(pairs)
        return pairs


def _attr(obj: Any, name: str) -> Any:
    return getattr(obj, name) if obj is not None else None


def _lesion_sim(gold: Zmiana, pred: Zmiana) -> float:
    return max(
        (_observation_sim(g, p) for g in gold.obserwacje for p in pred.obserwacje),
        default=0.0,
    )


def _observation_sim(gold: Obserwacja, pred: Obserwacja) -> float:
    return _quote_overlap(gold.cytat, pred.cytat) if gold.modalnosc == pred.modalnosc else 0.0


def _node_sim(gold: Wezel, pred: Wezel) -> float:
    return _quote_overlap(gold.cytat, pred.cytat) if gold.modalnosc == pred.modalnosc else 0.0


def _quote_overlap(a: str, b: str) -> float:
    return max(quote_similarity(a, fold(b)), quote_similarity(b, fold(a)))


def _same_text(a: str, b: str) -> bool:
    return text_similarity(a, b) >= TEXT_MIN_SIMILARITY
