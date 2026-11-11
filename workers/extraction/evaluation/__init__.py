"""Scoring extraction results (and OCR text) against hand-made ground truth."""

from ..errors import EvaluationDataError
from .compare import char_error_rate, evaluate
from .formatting import format_report
from .loading import load_gold, load_predictions, load_transcripts
from .report import Report
from .scores import EntityScore, FieldScore

__all__ = [
    "EntityScore",
    "EvaluationDataError",
    "FieldScore",
    "Report",
    "char_error_rate",
    "evaluate",
    "format_report",
    "load_gold",
    "load_predictions",
    "load_transcripts",
]
