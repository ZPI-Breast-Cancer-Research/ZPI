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
