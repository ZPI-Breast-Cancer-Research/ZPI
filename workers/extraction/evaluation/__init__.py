"""Scoring extraction results (and OCR text) against hand-made ground truth."""

from .compare import char_error_rate, evaluate
from .loading import load_gold, load_predictions, load_transcripts
from .report import format_report
from .scores import EntityScore, FieldScore, Report

__all__ = [
    "EntityScore",
    "FieldScore",
    "Report",
    "char_error_rate",
    "evaluate",
    "format_report",
    "load_gold",
    "load_predictions",
    "load_transcripts",
]
