import json
from pathlib import Path

from ..schema import EkstrakcjaBadania, ExtractionResult


def load_gold(directory: Path) -> dict[str, EkstrakcjaBadania]:
    gold = {}
    for path in sorted(directory.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        try:
            gold[path.stem] = EkstrakcjaBadania.model_validate(raw["data"])
        except (KeyError, ValueError) as exc:
            raise ValueError(f"{path.name}: not a valid gold file: {exc}") from exc
    return gold


def load_transcripts(directory: Path) -> dict[str, str]:
    """Hand-typed report texts (``<gold dir>/text/<name>.txt``), the reference for OCR."""
    return {
        path.stem: path.read_text(encoding="utf-8")
        for path in sorted((directory / "text").glob("*.txt"))
    }


def load_predictions(path: Path) -> dict[str, ExtractionResult]:
    results = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            result = ExtractionResult.model_validate_json(line)
            results[Path(result.source).stem] = result
    return results
