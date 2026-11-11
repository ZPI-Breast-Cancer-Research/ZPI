"""Scores of one kind of result and the metrics computed from them: a field, an entity type,
OCR text."""

from collections.abc import Iterable
from dataclasses import dataclass, field

from ..normalize import normalize_text


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
class OCRScore:
    """Character error rate (CER) of each OCR-read document against its hand-typed transcript.

    CER is an error rate: 0.0 is a perfect read, 0.05 means 5 % of the characters are wrong.
    """

    documents: dict[str, float] = field(default_factory=dict)

    def add(self, key: str, reference: str, hypothesis: str) -> None:
        self.documents[key] = self.char_error_rate(reference, hypothesis)

    @property
    def mean(self) -> float | None:
        return sum(self.documents.values()) / len(self.documents) if self.documents else None

    @property
    def worst(self) -> tuple[str, float] | None:
        """The document with the highest CER and its value."""
        if not self.documents:
            return None
        key = max(self.documents, key=self.documents.__getitem__)
        return key, self.documents[key]

    @staticmethod
    def char_error_rate(reference: str, hypothesis: str, *, normalize: bool = True) -> float:
        """Levenshtein distance / reference length, after the same normalisation as the LLM input
        and with all whitespace collapsed (line breaks are layout, not OCR errors).

        ``normalize=False`` skips ``normalize_text`` (whitespace is still collapsed), to measure
        how much the normalisation itself removes from the error.
        """
        prepare = normalize_text if normalize else str
        ref, hyp = (" ".join(prepare(t).split()) for t in (reference, hypothesis))
        if not ref:
            return 0.0 if not hyp else 1.0
        previous = list(range(len(hyp) + 1))
        for i, r in enumerate(ref, start=1):
            current = [i]
            for j, h in enumerate(hyp, start=1):
                current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h)))
            previous = current
        return previous[-1] / len(ref)
