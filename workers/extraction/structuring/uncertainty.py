"""Uncertainty of one extraction result: how much a doctor should doubt it, in [0, 1].

Higher means less certain (the same direction as the segmentation uncertainty), so the review
queue shows the least certain results first. It combines signals the pipeline already has, so
it costs no extra LLM call:

- ``error``: the extraction failed (1.0, so the whole uncertainty is 1.0)
- ``warnings``: values that do not follow from the report text (``checks.py``), weighted by how
  bad each kind is and divided by how much the document has to check
- ``ocr``: low OCR confidence of a scan (0 for text input)
- ``retry``: the first LLM answer was not valid JSON

The components are joined with a noisy-OR, ``1 - prod(1 - c)``: the result stays in [0, 1] and
one strong signal is enough to put a document high in the queue.

The weights are set here up front from what each warning means, not tuned on the ground truth:
with 12 gold documents any tuning would fit the noise.
"""

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..schema import ExtractionResult

HEAVY, MEDIUM, LIGHT = 1.0, 0.5, 0.25
# First matching phrase of a ``checks.py`` warning wins.
WARNING_WEIGHTS = (
    ("cytatu nie znaleziono", HEAVY),  # the quote is not in the report: made up
    ("nie występuje w cytacie", HEAVY),  # a size / distance / clock not in its quote
    ("nie wynika z cytatu", MEDIUM),  # shape, margin or echogenicity not in its quote
    ("dotyczy tylko USG", MEDIUM),  # a USG-only field on a mammography observation
    ("zmiany_ogniskowe = false", MEDIUM),  # a lesion in a breast "without focal lesions"
    ("w opisie brak słów", LIGHT),  # a verbatim field with words not in the text, often OCR
)
# Structural warnings: repeated lesion ids, observations without polaczenie_obserwacji.
DEFAULT_WEIGHT = LIGHT
# One heavy warning in a document with one lesion seen in MMG and USG (3 items) gives ~0.49.
WARNINGS_K = 2.0
# PaddleOCR reports ~0.9-0.99 per line, so the scale starts below a clean scan.
OCR_GOOD = 0.95
OCR_SPAN = 0.15
RETRY = 0.2

COMPONENTS = ("error", "warnings", "ocr", "retry")


def warning_weight(warning: str) -> float:
    return next((w for phrase, w in WARNING_WEIGHTS if phrase in warning), DEFAULT_WEIGHT)


def components(result: "ExtractionResult") -> dict[str, float]:
    """Each signal in [0, 1]; the keys are ``COMPONENTS``."""
    return {
        "error": 1.0 if result.status != "ok" or result.data is None else 0.0,
        "warnings": _warnings(result),
        "ocr": _ocr(result.provenance.ocr_mean_confidence),
        "retry": RETRY if result.attempts > 1 and result.status == "ok" else 0.0,
    }


def uncertainty(result: "ExtractionResult") -> float:
    return combine(components(result))


def combine(parts: dict[str, float]) -> float:
    """Noisy-OR of the components, rounded to 3 places."""
    return round(1.0 - math.prod(1.0 - p for p in parts.values()), 3)


def _warnings(result: "ExtractionResult") -> float:
    if not result.warnings:
        return 0.0
    # Items the checks look at: the document itself (breasts, conclusion), every observation
    # and every node. A long report has more chances to get a warning than a short one.
    items = 1
    if result.data is not None:
        items += sum(len(z.obserwacje) for z in result.data.zmiany) + len(result.data.wezly)
    weight = sum(warning_weight(w) for w in result.warnings)
    return round(1.0 - math.exp(-WARNINGS_K * weight / items), 3)


def _ocr(confidence: float | None) -> float:
    if confidence is None:
        return 0.0
    return round(min(1.0, max(0.0, (OCR_GOOD - confidence) / OCR_SPAN)), 3)
