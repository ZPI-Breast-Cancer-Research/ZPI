"""Save the OCR metrics of an evaluation run in an OCR version (module_version.metrics).

    python -m workers.extraction run data/reports --out preds.jsonl      # OCR + LLM
    python -m workers.extraction eval preds.jsonl --report scores.json   # against transcripts
    python manage.py save_ocr_metrics 1 scores.json --dataset gold-v2

The run has to use the configuration of that version (engine and settings); the command only
records the numbers.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from mlops.models import ModelVersion

# metrics are written for a draft and as the baseline of the version in use; a proposal is
# frozen until it is decided
WRITABLE = (ModelVersion.StatusChoices.NEW, ModelVersion.StatusChoices.PRODUCTION)
KEYS = ("cer", "word_error", "worst_cer", "mean_confidence", "seconds_per_page")


class Command(BaseCommand):
    help = "Save the OCR metrics of an evaluation report (eval --report) in an OCR version."

    def add_arguments(self, parser):
        parser.add_argument("version", help="version of the module ocr, e.g. 1")
        parser.add_argument("report", type=Path, help="JSON written by `eval --report`")
        parser.add_argument("--dataset", required=True, help="name of the set with transcripts")

    def handle(self, *args, version, report, dataset, **options):
        try:
            scores = json.loads(report.read_text(encoding="utf-8"))["ocr_metrics"]
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(f"{report}: no OCR metrics ({exc})") from exc
        if not scores.get("cases"):
            raise CommandError(f"{report}: no document was read by OCR with a transcript")

        model = ModelVersion.objects.filter(
            module=ModelVersion.ModuleChoices.OCR, version=version
        ).first()
        if model is None:
            raise CommandError(f"No OCR version {version}")
        if model.status not in WRITABLE:
            raise CommandError(
                f"OCR version {version} is {model.status}; its metrics stay as they are"
            )

        model.metrics = {key: scores.get(key) for key in KEYS}
        model.metrics_cases = scores["cases"]
        model.dataset = dataset
        model.save(update_fields=["metrics", "metrics_cases", "dataset"])
        self.stdout.write(
            f"OCR {version}: CER {scores.get('cer'):.1%} on {scores['cases']} documents ({dataset})"
        )
