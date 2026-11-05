from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

SUMMARY_GROUPS = (
    "piersi", "obserwacja.mammografia", "obserwacja.usg", "zmiana", "wezel", "wniosek"
)


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

    @property
    def precision(self) -> float | None:
        """Of the values the model filled in, the share that is right (spurious lowers it)."""
        predicted = self.correct + self.wrong + self.spurious
        return self.correct / predicted if predicted else None

    @property
    def recall(self) -> float | None:
        """Of the values in the gold data, the share the model got right (missed lowers it)."""
        expected = self.correct + self.wrong + self.missed
        return self.correct / expected if expected else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None:
            return None
        return 2 * p * r / (p + r) if p + r else 0.0

    @classmethod
    def pooled(cls, scores: Iterable["FieldScore"]) -> "FieldScore":
        total = cls()
        for s in scores:
            total.correct += s.correct
            total.wrong += s.wrong
            total.missed += s.missed
            total.spurious += s.spurious
        return total


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
            "fields": scores(self.fields, ("n", "accuracy", "precision", "recall", "f1")),
            "ocr_cer": {"mean": self.mean_ocr_cer, "documents": self.ocr_cer},
        }
