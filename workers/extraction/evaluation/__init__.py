"""Scoring extraction results (and OCR text) against hand-made ground truth."""

from ..errors import EvaluationDataError
from .formatting import format_experiment_diff, format_experiments, format_report
from .loading import load_gold, load_predictions, load_transcripts
from .report import Report
from .scores import EntityScore, FieldScore, OCRScore
from .scoring import evaluate

__all__ = [
    "EntityScore",
    "EvaluationDataError",
    "FieldScore",
    "OCRScore",
    "Report",
    "evaluate",
    "format_experiment_diff",
    "format_experiments",
    "format_report",
    "load_gold",
    "load_predictions",
    "load_transcripts",
]
