"""Scores of one kind of result and the metrics computed from them: a field, an entity type,
OCR text, uncertainty."""

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from ..normalize import normalize_text
from ..structuring.uncertainty import COMPONENTS


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
        """None only when there is nothing to score; 0.0 when nothing was matched."""
        p, r = self.precision, self.recall
        if p is None and r is None:
            return None
        p, r = p or 0.0, r or 0.0
        return 2 * p * r / (p + r) if p + r else 0.0


@dataclass
class OCRScore:
    """OCR quality of each OCR-read document against its hand-typed transcript.

    Two error rates (0.0 is a perfect read, 0.05 means 5 % wrong):

    - ``documents``: character error rate (CER). It counts a line OCR read in the wrong place
      twice (deleted where it should be, inserted where it was read).
    - ``words``: order-insensitive word error rate (bag of words). It ignores where a word was
      read, so a high CER with a low ``words`` rate means the text is right but out of order.
    """

    documents: dict[str, float] = field(default_factory=dict)
    words: dict[str, float] = field(default_factory=dict)

    def add(self, key: str, reference: str, hypothesis: str) -> None:
        self.documents[key] = self.char_error_rate(reference, hypothesis)
        self.words[key] = self.bag_of_words_error_rate(reference, hypothesis)

    @property
    def mean(self) -> float | None:
        """Mean CER."""
        return sum(self.documents.values()) / len(self.documents) if self.documents else None

    @property
    def words_mean(self) -> float | None:
        """Mean order-insensitive word error rate."""
        return sum(self.words.values()) / len(self.words) if self.words else None

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

    @staticmethod
    def bag_of_words_error_rate(
        reference: str, hypothesis: str, *, normalize: bool = True
    ) -> float:
        """Word error rate that ignores word order: the words of both texts as multisets.

        ``(max(len(ref), len(hyp)) - common) / len(ref)``, so a wrong word read in place of a right
        one is one error (like a substitution in WER), and a missing or extra word is one error.
        Same normalisation as ``char_error_rate``; punctuation stays part of the word.
        """
        prepare = normalize_text if normalize else str
        ref, hyp = (Counter(prepare(t).split()) for t in (reference, hypothesis))
        n_ref, n_hyp = ref.total(), hyp.total()
        if not n_ref:
            return 0.0 if not n_hyp else 1.0
        common = (ref & hyp).total()
        return (max(n_ref, n_hyp) - common) / n_ref


@dataclass
class UncertaintyScore:
    """Does ``uncertainty`` rank documents by how wrong their extraction is?

    Per document: the uncertainty, its components and the error rate (share of the compared
    fields and paired items that are not correct). The review queue needs the right order,
    not calibrated values, so the measures are rank-based:

    - ``rho``: Spearman correlation of uncertainty with the error rate (1.0 = same order)
    - ``top_k_hits``: of the k most uncertain documents, how many are among the k worst
    """

    uncertainty: dict[str, float] = field(default_factory=dict)
    components: dict[str, dict[str, float]] = field(default_factory=dict)
    errors: dict[str, float] = field(default_factory=dict)

    def add(self, key: str, uncertainty: float, components: dict[str, float], doc: FieldScore):
        self.uncertainty[key] = uncertainty
        self.components[key] = components
        self.errors[key] = 1.0 - doc.accuracy if doc.accuracy is not None else 0.0

    def rho(self, component: str | None = None) -> float | None:
        """Spearman correlation with the error rate, of the whole uncertainty or one component.

        None with fewer than 3 documents or when either side is constant (e.g. no OCR).
        """
        keys = sorted(self.errors)
        if component is None:
            values = [self.uncertainty[k] for k in keys]
        else:
            values = [self.components[k].get(component, 0.0) for k in keys]
        return spearman(values, [self.errors[k] for k in keys])

    def component_rho(self) -> dict[str, float | None]:
        return {name: self.rho(name) for name in COMPONENTS}

    def top_k_hits(self, k: int = 3) -> tuple[int, int] | None:
        """(hits, k): the k most uncertain documents that are among the k with most errors."""
        k = min(k, len(self.errors))
        if not k:
            return None
        worst = set(sorted(self.errors, key=lambda key: -self.errors[key])[:k])
        doubted = sorted(self.uncertainty, key=lambda key: -self.uncertainty[key])[:k]
        return len(worst.intersection(doubted)), k


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Spearman rank correlation, ties get their average rank."""
    if len(x) != len(y) or len(x) < 3:
        return None
    rx, ry = _ranks(x), _ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if not sx or not sy:
        return None
    return cov / (sx * sy)


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for position in range(i, j + 1):
            ranks[order[position]] = (i + j) / 2 + 1
        i = j + 1
    return ranks
