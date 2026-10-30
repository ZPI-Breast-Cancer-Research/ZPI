import json
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, TypeVar

from .checks import fold, quote_similarity
from .normalize import normalize_text
from .prompting import load_few_shot
from .schema import EkstrakcjaBadania, ExtractionResult, Obserwacja, Wezel, Wymiary, Zmiana

TEXT_MIN_SIMILARITY = 0.9
MATCH_MIN_SIMILARITY = 0.6
LEAK_MIN_SIMILARITY = 0.85
PIERS_FLAGS = ("obrzek", "zwapnienia", "mikrozwapnienia", "zmiany_ogniskowe")
OBS_EXACT = ("godzina", "ksztalt", "brzeg", "echogenicznosc", "jednorodnosc", "naciek_skory")
SUMMARY_GROUPS = (
    "piersi", "obserwacja.mammografia", "obserwacja.usg", "zmiana", "wezel", "wniosek"
)

T = TypeVar("T")


@dataclass
class FieldScore:
    correct: int = 0
    wrong: int = 0
    missed: int = 0
    spurious: int = 0

    @property
    def n(self) -> int:
        return self.correct + self.wrong + self.missed + self.spurious

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.n if self.n else None


@dataclass
class EntityScore:
    gold: int = 0
    predicted: int = 0
    matched: int = 0

    @property
    def precision(self) -> float | None:
        return self.matched / self.predicted if self.predicted else None

    @property
    def recall(self) -> float | None:
        return self.matched / self.gold if self.gold else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p and r else None


@dataclass
class Report:
    evaluated: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: dict[str, list[str]] = field(default_factory=dict)
    provenance: list[dict[str, str]] = field(default_factory=list)
    entities: dict[str, EntityScore] = field(default_factory=dict)
    fields: dict[str, FieldScore] = field(default_factory=dict)
    ocr_cer: dict[str, float] = field(default_factory=dict)

    @property
    def mean_ocr_cer(self) -> float | None:
        return sum(self.ocr_cer.values()) / len(self.ocr_cer) if self.ocr_cer else None

    def field_score(self, name: str) -> FieldScore:
        return self.fields.setdefault(name, FieldScore())

    def entity_score(self, name: str) -> EntityScore:
        return self.entities.setdefault(name, EntityScore())

    def summary(self) -> dict[str, float | None]:
        """Headline numbers for comparing runs: pooled field accuracy, per group and entity F1."""
        summary = {"field_accuracy": _pooled_accuracy(self.fields.values())}
        for group in SUMMARY_GROUPS:
            summary[f"{group}_accuracy"] = _pooled_accuracy(
                s for name, s in self.fields.items() if name.startswith(group + ".")
            )
        for entity in ("zmiany", "obserwacje", "wezly"):
            score = self.entities.get(entity)
            summary[f"{entity}_f1"] = score.f1 if score else None
        birads = self.fields.get("wniosek.birads")
        summary["wniosek_birads_accuracy"] = birads.accuracy if birads else None
        summary["ocr_cer"] = self.mean_ocr_cer
        return summary

    def to_dict(self) -> dict[str, Any]:
        def scores(items: dict[str, Any], props: tuple[str, ...]) -> dict[str, Any]:
            return {
                name: {**asdict(score), **{p: getattr(score, p) for p in props}}
                for name, score in sorted(items.items())
            }

        return {
            "evaluated": self.evaluated,
            "errors": self.errors,
            "skipped": self.skipped,
            "provenance": self.provenance,
            "summary": self.summary(),
            "entities": scores(self.entities, ("precision", "recall", "f1")),
            "fields": scores(self.fields, ("n", "accuracy")),
            "ocr_cer": {"mean": self.mean_ocr_cer, "documents": self.ocr_cer},
        }


def _pooled_accuracy(scores: Iterable[FieldScore]) -> float | None:
    correct = total = 0
    for score in scores:
        correct += score.correct
        total += score.n
    return correct / total if total else None


def load_gold(directory: Path) -> dict[str, EkstrakcjaBadania]:
    gold = {}
    for path in sorted(directory.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        try:
            gold[path.stem] = EkstrakcjaBadania.model_validate(raw["data"])
        except (KeyError, ValueError) as exc:
            raise ValueError(f"{path.name}: not a valid gold file: {exc}") from exc
    return gold


def load_transcripts(directory: Path) -> dict[str, str]:
    """Hand-typed report texts (``<gold dir>/text/<name>.txt``), the reference for OCR."""
    return {
        path.stem: path.read_text(encoding="utf-8")
        for path in sorted((directory / "text").glob("*.txt"))
    }


def load_predictions(path: Path) -> dict[str, ExtractionResult]:
    results = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            result = ExtractionResult.model_validate_json(line)
            results[Path(result.source).stem] = result
    return results


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


def char_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein distance / reference length, after the same normalisation as the LLM input
    and with all whitespace collapsed (line breaks are layout, not OCR errors)."""
    ref, hyp = (" ".join(normalize_text(t).split()) for t in (reference, hypothesis))
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
    """Greedy one-to-one matching, best pairs first; pairs below the threshold stay unmatched."""
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
    # Containment either way: the model often quotes a little more or less than the annotator.
    return max(quote_similarity(a, fold(b)), quote_similarity(b, fold(a)))


def _same_text(a: str, b: str) -> bool:
    return SequenceMatcher(None, fold(a), fold(b), autojunk=False).ratio() >= TEXT_MIN_SIMILARITY


def format_report(report: Report) -> str:
    lines = []
    for p in report.provenance:
        lines.append(
            f"model: {p['llm_model'] or '?'} | prompt: {p['prompt_version']} | "
            f"schema: {p['schema_version']}"
        )
    skipped = ", ".join(
        f"{reason} {len(keys)} ({', '.join(keys)})" for reason, keys in report.skipped.items()
    )
    summary = f"documents: {len(report.evaluated)} evaluated"
    if report.errors:
        summary += f" (failed, scored as empty: {', '.join(report.errors)})"
    lines.append(summary + (f"; skipped: {skipped}" if skipped else ""))
    if report.ocr_cer:
        worst = max(report.ocr_cer, key=report.ocr_cer.__getitem__)
        lines.append(
            f"OCR character error rate: mean {report.mean_ocr_cer:.1%}, "
            f"worst {report.ocr_cer[worst]:.1%} ({worst})"
        )

    lines += ["", "summary"]
    lines += [
        f"  {name:<36}{_pct(value).strip():>6}"
        for name, value in report.summary().items()
        if name != "ocr_cer"
    ]

    lines += ["", f"{'entity':<14}{'gold':>6}{'pred':>6}{'match':>7}{'P':>7}{'R':>7}{'F1':>7}"]
    for name, e in report.entities.items():
        lines.append(
            f"{name:<14}{e.gold:>6}{e.predicted:>6}{e.matched:>7}"
            f"{_pct(e.precision)}{_pct(e.recall)}{_pct(e.f1)}"
        )

    width = max((len(name) for name in report.fields), default=10) + 2
    lines += [
        "",
        f"{'field':<{width}}{'n':>5}{'acc':>7}{'wrong':>7}{'missed':>8}{'spurious':>10}",
    ]
    for name, s in sorted(report.fields.items()):
        lines.append(
            f"{name:<{width}}{s.n:>5}{_pct(s.accuracy)}{s.wrong:>7}{s.missed:>8}{s.spurious:>10}"
        )
    return "\n".join(lines)


def _pct(value: float | None) -> str:
    return f"{value:>7.0%}" if value is not None else f"{'–':>7}"
