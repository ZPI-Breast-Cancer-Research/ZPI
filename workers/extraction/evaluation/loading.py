import json
from pathlib import Path

from ..errors import EvaluationDataError
from ..schema import EkstrakcjaBadania, ExtractionResult


def load_gold(directory: Path) -> dict[str, EkstrakcjaBadania]:
    """Hand-typed jsons as a reference for perfect extraction"""
    gold = {}
    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            gold[path.stem] = EkstrakcjaBadania.model_validate(raw["data"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EvaluationDataError(f"{path.name}: not a valid gold file: {exc}") from exc
    return gold


def load_transcripts(directory: Path) -> dict[str, str]:
    """Hand-typed report texts (``<gold dir>/text/<name>.txt``), the reference for OCR."""
    return {
        path.stem: path.read_text(encoding="utf-8")
        for path in sorted((directory / "text").glob("*.txt"))
    }


def load_predictions(path: Path) -> dict[str, ExtractionResult]:
    results = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            result = ExtractionResult.model_validate_json(line)
        except ValueError as exc:
            raise EvaluationDataError(
                f"{path.name}, line {number}: not a valid prediction: {exc}"
            ) from exc
        results[Path(result.source).stem] = result
    return results
