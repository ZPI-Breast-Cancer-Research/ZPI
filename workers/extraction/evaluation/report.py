"""Scores of a whole evaluation run: per field, per entity, OCR, and the summary."""

from dataclasses import asdict, dataclass, field
from typing import Any

from .scores import EntityScore, FieldScore, OCRScore

SUMMARY_GROUPS = (
    "piersi",
    "obserwacja.mammografia",
    "obserwacja.usg",
    "zmiana",
    "wezel",
    "wniosek",
)


@dataclass
class Report:
    evaluated: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: dict[str, list[str]] = field(default_factory=dict)
    provenance: list[dict[str, str]] = field(default_factory=list)
    entities: dict[str, EntityScore] = field(default_factory=dict)
    fields: dict[str, FieldScore] = field(default_factory=dict)
    ocr: OCRScore = field(default_factory=OCRScore)

    def field_score(self, name: str) -> FieldScore:
        return self.fields.setdefault(name, FieldScore())

    def entity_score(self, name: str) -> EntityScore:
        return self.entities.setdefault(name, EntityScore())

    def group_score(self, group: str | None = None) -> FieldScore:
        """All field scores pooled, or only those of one ``SUMMARY_GROUPS`` group."""
        return FieldScore.pooled(
            s for name, s in self.fields.items() if group is None or name.startswith(group + ".")
        )

    def summary(self) -> dict[str, float | None]:
        """Headline numbers for comparing runs: pooled field accuracy, per group and entity F1."""
        overall = self.group_score()
        summary = {
            "field_accuracy": overall.accuracy,
            "field_precision": overall.precision,
            "field_recall": overall.recall,
            "field_f1": overall.f1,
        }
        for group in SUMMARY_GROUPS:
            summary[f"{group}_accuracy"] = self.group_score(group).accuracy
        for entity in ("zmiany", "obserwacje", "wezly"):
            score = self.entities.get(entity)
            summary[f"{entity}_f1"] = score.f1 if score else None
        birads = self.fields.get("wniosek.birads")
        summary["wniosek_birads_accuracy"] = birads.accuracy if birads else None
        summary["ocr_cer"] = self.ocr.mean
        summary["ocr_bow_wer"] = self.ocr.words_mean
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
            "fields": scores(self.fields, ("n", "accuracy", "precision", "recall", "f1")),
            "ocr_cer": {"mean": self.ocr.mean, "documents": self.ocr.documents},
            "ocr_bow_wer": {"mean": self.ocr.words_mean, "documents": self.ocr.words},
        }
