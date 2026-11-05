import math
from collections.abc import Callable, Sequence
from difflib import SequenceMatcher
from typing import Any, TypeVar

from ..normalize import fold, normalize_text, quote_similarity
from ..schema import EkstrakcjaBadania, ExtractionResult, Obserwacja, Wezel, Wymiary, Zmiana
from ..structuring.prompting import load_few_shot
from .scores import Report

TEXT_MIN_SIMILARITY = 0.9
MATCH_MIN_SIMILARITY = 0.6
LEAK_MIN_SIMILARITY = 0.85
PIERS_FLAGS = ("obrzek", "zwapnienia", "mikrozwapnienia", "zmiany_ogniskowe")
OBS_EXACT = ("godzina", "ksztalt", "brzeg", "echogenicznosc", "jednorodnosc", "naciek_skory")

T = TypeVar("T")


def evaluate(
    gold: dict[str, EkstrakcjaBadania],
    predictions: dict[str, ExtractionResult],
    *,
    transcripts: dict[str, str] | None = None,
    include_leaked: bool = False,
) -> Report:
    report = Report()
    skip = report.skipped
    few_shot_reports = [example for example, _ in load_few_shot()]

    for key in sorted(predictions.keys() - gold.keys()):
        skip.setdefault("no_gold", []).append(key)
    for key in sorted(gold):
        result = predictions.get(key)
        if result is None:
            skip.setdefault("no_prediction", []).append(key)
            continue
        if not include_leaked and _is_few_shot(result.text, few_shot_reports):
            skip.setdefault("few_shot_leak", []).append(key)
            continue
        report.evaluated.append(key)
        provenance = {
            "llm_model": result.provenance.llm_model,
            "prompt_version": result.provenance.prompt_version,
            "schema_version": result.provenance.schema_version,
        }
        if provenance not in report.provenance:
            report.provenance.append(provenance)
        reference = (transcripts or {}).get(key)
        if reference and result.provenance.ocr_engine and result.text:
            report.ocr_cer[key] = char_error_rate(reference, result.text)
        if result.status != "ok" or result.data is None:
            # A failed document counts as nothing found.
            report.errors.append(key)
            _compare_document(report, gold[key], EkstrakcjaBadania(modalnosci=[]))
        else:
            _compare_document(report, gold[key], result.data)
    return report


def char_error_rate(reference: str, hypothesis: str, *, normalize: bool = True) -> float:
    """Levenshtein distance / reference length, after the same normalisation as the LLM input
    and with all whitespace collapsed (line breaks are layout, not OCR errors).

    ``normalize=False`` skips ``normalize_text`` (whitespace is still collapsed), to measure
    how much the normalisation itself removes from the error.
    """
    prepare = normalize_text if normalize else str
    ref, hyp = (" ".join(prepare(t).split()) for t in (reference, hypothesis))
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        current = [i]
        for j, h in enumerate(hyp, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h)))
        previous = current
    return previous[-1] / len(ref)


def _is_few_shot(text: str, few_shot_reports: list[str]) -> bool:
    haystack = fold(text)
    return any(quote_similarity(r, haystack) >= LEAK_MIN_SIMILARITY for r in few_shot_reports)


def _compare_document(report: Report, gold: EkstrakcjaBadania, pred: EkstrakcjaBadania) -> None:
    _score(report, "modalnosci", set(gold.modalnosci) or None, set(pred.modalnosci) or None)

    for side in ("lewa", "prawa"):
        g, p = getattr(gold.piersi, side), getattr(pred.piersi, side)
        _score(report, "piersi.budowa", g.budowa, p.budowa, _same_text)
        for name in PIERS_FLAGS:
            _score(report, f"piersi.{name}", getattr(g, name), getattr(p, name))
        _score(report, "piersi.skora.stan", g.skora.stan, p.skora.stan, _same_text)
        _score(report, "piersi.skora.naciek", g.skora.naciek, p.skora.naciek)

    _score(report, "wniosek.birads", gold.wniosek.birads, pred.wniosek.birads)
    _score(report, "wniosek.tekst", gold.wniosek.tekst, pred.wniosek.tekst, _same_text)
    _score(report, "wniosek.zalecenie", gold.wniosek.zalecenie, pred.wniosek.zalecenie, _same_text)

    for g_lesion, p_lesion in _match(report, "zmiany", gold.zmiany, pred.zmiany, _lesion_sim):
        _compare_lesion(report, g_lesion, p_lesion)
    for g_node, p_node in _match(report, "wezly", gold.wezly, pred.wezly, _node_sim):
        _compare_node(report, g_node, p_node)


def _compare_lesion(report: Report, gold: Zmiana, pred: Zmiana) -> None:
    _score(report, "zmiana.strona", gold.strona, pred.strona)
    _score(report, "zmiana.birads", gold.birads, pred.birads)
    _score(
        report,
        "zmiana.polaczenie_obserwacji.pewne",
        gold.polaczenie_obserwacji and gold.polaczenie_obserwacji.pewne,
        pred.polaczenie_obserwacji and pred.polaczenie_obserwacji.pewne,
    )
    for g_obs, p_obs in _match(
        report, "obserwacje", gold.obserwacje, pred.obserwacje, _observation_sim
    ):
        _compare_observation(report, g_obs, p_obs)


def _compare_observation(report: Report, gold: Obserwacja, pred: Obserwacja) -> None:
    prefix = f"obserwacja.{gold.modalnosc}"
    _score(
        report,
        f"{prefix}.lokalizacje",
        {fold(x) for x in gold.lokalizacje} or None,
        {fold(x) for x in pred.lokalizacje} or None,
    )
    _score(report, f"{prefix}.typ", gold.typ, pred.typ, _same_text)
    for name in OBS_EXACT:
        _score(report, f"{prefix}.{name}", getattr(gold, name), getattr(pred, name))
    for name in ("odleglosc_od_brodawki", "glebokosc"):
        g, p = getattr(gold, name), getattr(pred, name)
        _score(report, f"{prefix}.{name}", g and g.mm(), p and p.mm(), math.isclose)
    _compare_dimensions(report, prefix, gold.wymiary, pred.wymiary)


def _compare_node(report: Report, gold: Wezel, pred: Wezel) -> None:
    _score(report, "wezel.strona", gold.strona, pred.strona)
    _score(report, "wezel.okolica", gold.okolica, pred.okolica, _same_text)
    _score(report, "wezel.liczba", gold.liczba, pred.liczba)
    _score(report, "wezel.patologiczne", gold.patologiczne, pred.patologiczne)
    _score(report, "wezel.uwagi", gold.uwagi, pred.uwagi, _same_text)
    _compare_dimensions(report, "wezel", gold.wymiary, pred.wymiary)


def _compare_dimensions(
    report: Report, prefix: str, gold: Wymiary | None, pred: Wymiary | None
) -> None:
    for name in ("wartosci", "jednostka", "kwalifikator"):
        _score(report, f"{prefix}.wymiary.{name}", _attr(gold, name), _attr(pred, name))
    _score(
        report,
        f"{prefix}.wymiary.max_mm",
        gold and gold.max_mm(),
        pred and pred.max_mm(),
        math.isclose,
    )


def _attr(obj: Any, name: str) -> Any:
    return getattr(obj, name) if obj is not None else None


def _score(
    report: Report,
    name: str,
    gold: Any,
    pred: Any,
    same: Callable[[Any, Any], bool] = lambda a, b: a == b,
) -> None:
    if gold is None and pred is None:
        return
    score = report.field_score(name)
    if gold is None:
        score.spurious += 1
    elif pred is None:
        score.missed += 1
    elif same(gold, pred):
        score.correct += 1
    else:
        score.wrong += 1


def _match(
    report: Report,
    entity: str,
    gold: Sequence[T],
    pred: Sequence[T],
    similarity: Callable[[T, T], float],
) -> list[tuple[T, T]]:
  
    candidates = sorted(
        (
            (similarity(g, p), i, j)
            for i, g in enumerate(gold)
            for j, p in enumerate(pred)
        ),
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

    counts = report.entity_score(entity)
    counts.gold += len(gold)
    counts.predicted += len(pred)
    counts.matched += len(pairs)
    return pairs


def _lesion_sim(gold: Zmiana, pred: Zmiana) -> float:
    return max(
        (
            _observation_sim(g, p)
            for g in gold.obserwacje
            for p in pred.obserwacje
        ),
        default=0.0,
    )


def _observation_sim(gold: Obserwacja, pred: Obserwacja) -> float:
    return _quote_overlap(gold.cytat, pred.cytat) if gold.modalnosc == pred.modalnosc else 0.0


def _node_sim(gold: Wezel, pred: Wezel) -> float:
    return _quote_overlap(gold.cytat, pred.cytat) if gold.modalnosc == pred.modalnosc else 0.0


def _quote_overlap(a: str, b: str) -> float:
    return max(quote_similarity(a, fold(b)), quote_similarity(b, fold(a)))


def _same_text(a: str, b: str) -> bool:
    return SequenceMatcher(None, fold(a), fold(b), autojunk=False).ratio() >= TEXT_MIN_SIMILARITY
