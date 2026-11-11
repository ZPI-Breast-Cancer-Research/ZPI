"""Counters of one field or one entity type, and the metrics computed from them."""

from collections.abc import Iterable
from dataclasses import dataclass


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
