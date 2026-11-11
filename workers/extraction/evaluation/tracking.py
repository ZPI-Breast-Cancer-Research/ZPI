import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from ..config import Settings
from ..schema import SCHEMA_VERSION, ExtractionResult, llm_json_schema
from ..structuring.prompting import PROMPT_VERSION, load_few_shot, system_prompt
from .report import Report

EXPERIMENTS_DIR = Path(__file__).parents[1] / "experiments" / "runs"
REPO_ROOT = Path(__file__).resolve().parents[3]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "run"


def next_id() -> str:
    numbers = [int(p.name[:3]) for p in EXPERIMENTS_DIR.glob("[0-9][0-9][0-9]_*.json")]
    return f"{max(numbers, default=0) + 1:03d}"


def build_record(
    exp_id: str,
    name: str,
    *,
    hypothesis: str | None,
    settings: Settings,
    results: list[ExtractionResult],
    report: Report,
    gold_dir: Path,
    predictions: Path,
) -> dict[str, Any]:
    ok = [r for r in results if r.status == "ok"]
    first = (ok or results)[0].provenance if results else None
    scans = any(r.provenance.ocr_engine for r in results)
    # What produced the results, not the current settings: with --predictions they may differ.
    # None when the results predate these provenance fields.
    few_shot: int | None
    structured_output: bool | None
    if first is None:
        few_shot, structured_output = settings.few_shot_examples, settings.llm_structured_output
    else:
        few_shot, structured_output = first.few_shot, first.structured_output
    # The hash is known only for the current prompt and a known number of examples.
    same_prompt = first is None or first.prompt_version == PROMPT_VERSION
    prompt_sha = (
        _sha(json.dumps([system_prompt(), load_few_shot()[:few_shot]], ensure_ascii=False))
        if same_prompt and few_shot is not None
        else None
    )
    return {
        "id": exp_id,
        "name": name,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "hypothesis": hypothesis,
        "input": "scans" if scans else "transcripts",
        "config": {
            "llm_provider": first.llm_provider if first else settings.llm_provider,
            "llm_model": (first.llm_model if first else "") or settings.llm_model or None,
            "few_shot": few_shot,
            "structured_output": structured_output,
            "ocr_engine": first.ocr_engine if scans and first else None,
            "ocr_engine_version": first.ocr_engine_version if scans and first else None,
            "ocr_orientation": first.orientation_detector if scans and first else None,
            "prompt_version": first.prompt_version if first else PROMPT_VERSION,
            "prompt_sha": prompt_sha,
            "schema_version": first.schema_version if first else SCHEMA_VERSION,
            "schema_sha": _sha(json.dumps(llm_json_schema(), sort_keys=True)),
        },
        "code": git_state(),
        "data": {"gold_sha": gold_sha(gold_dir), "documents": len(report.evaluated)},
        "predictions": predictions.as_posix(),
        "runtime": {
            "failed": len(results) - len(ok),
            "llm_seconds_mean": _mean(r.llm_seconds for r in results),
            "ocr_seconds_mean": _mean(r.ocr_seconds for r in results),
        },
        "summary": report.summary(),
        "results": report.to_dict(),
    }


def save_record(record: dict[str, Any]) -> Path:
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPERIMENTS_DIR / f"{record['id']}_{slugify(record['name'])}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_records() -> list[dict[str, Any]]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(EXPERIMENTS_DIR.glob("[0-9][0-9][0-9]_*.json"))
    ]


def git_state() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return out.stdout.strip()

    commit = git("rev-parse", "--short", "HEAD")
    # The records themselves live in the module, so they must not make every run look dirty.
    status = git(
        "status",
        "--porcelain",
        "--",
        "workers/extraction",
        ":!workers/extraction/experiments",
    )
    return {"git_commit": commit, "git_dirty": bool(status) if status is not None else None}


def gold_sha(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted([*directory.glob("*.json"), *directory.glob("text/*.txt")]):
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _mean(values: Any) -> float | None:
    present = [v for v in values if v is not None]
    return round(mean(present), 2) if present else None


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
