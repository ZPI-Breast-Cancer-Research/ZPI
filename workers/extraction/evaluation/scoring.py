"""Evaluation run: which documents to score and what to record about the run."""

from ..matching import fold, quote_similarity
from ..schema import EkstrakcjaBadania, ExtractionResult
from ..structuring.prompting import load_few_shot
from .comparison import Comparison
from .report import Report

LEAK_MIN_SIMILARITY = 0.85


def evaluate(
    gold: dict[str, EkstrakcjaBadania],
    predictions: dict[str, ExtractionResult],
    *,
    transcripts: dict[str, str] | None = None,
    include_leaked: bool = False,
) -> Report:
    comparison = Comparison()
    report = comparison.report
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
            report.ocr.add(key, reference, result.text)
        if result.status != "ok" or result.data is None:
            # A failed document counts as nothing found.
            report.errors.append(key)
            doc = comparison.document(gold[key], EkstrakcjaBadania(modalnosci=[]))
        else:
            doc = comparison.document(gold[key], result.data)
        report.uncertainty.add(key, result.uncertainty, result.uncertainty_components, doc)
    return report


def _is_few_shot(text: str, few_shot_reports: list[str]) -> bool:
    haystack = fold(text)
    return any(quote_similarity(r, haystack) >= LEAK_MIN_SIMILARITY for r in few_shot_reports)
