"""Experiment history: one JSON record per evaluated run, versioned in git.

A record holds what produced the run (model, prompt and schema fingerprints, git commit, gold set)
and its scores – never report text, so it is safe to commit. Predictions stay in data/eval/runs/.
"""

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from .config import Settings
from .evaluation import Report
from .prompting import PROMPT_VERSION, load_few_shot, system_prompt
from .schema import SCHEMA_VERSION, ExtractionResult, llm_json_schema

EXPERIMENTS_DIR = Path(__file__).parent / "experiments" / "runs"
REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE_METRICS = (
    ("field_accuracy", "fields"),
    ("zmiany_f1", "lesF1"),
    ("wezly_f1", "nodeF1"),
    ("wniosek_birads_accuracy", "birads"),
    ("ocr_cer", "CER"),
)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "run"


def next_id() -> str:
    numbers = [int(p.name[:3]) for p in EXPERIMENTS_DIR.glob("[0-9][0-9][0-9]_*.json")]
    return f"{max(numbers, default=0) + 1:03d}"


def build_record(
    exp_id: str,
    name: str,
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
    few_shot = load_few_shot()[: settings.few_shot_examples]
    # A run recorded from older predictions may come from another prompt; its hash is unknown.
    same_prompt = first is None or first.prompt_version == PROMPT_VERSION
    return {
        "id": exp_id,
        "name": name,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "hypothesis": hypothesis,
        "input": "scans" if scans else "transcripts",
        "config": {
            "llm_provider": first.llm_provider if first else settings.llm_provider,
            "llm_model": (first.llm_model if first else "") or settings.llm_model or None,
            "few_shot": settings.few_shot_examples,
            "structured_output": settings.llm_structured_output,
            "ocr_engine": first.ocr_engine if scans and first else None,
            "ocr_engine_version": first.ocr_engine_version if scans and first else None,
            "ocr_orientation": first.orientation_detector if scans and first else None,
            "prompt_version": first.prompt_version if first else PROMPT_VERSION,
            "prompt_sha": _sha(json.dumps([system_prompt(), few_shot], ensure_ascii=False))
            if same_prompt
            else None,
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
        "status", "--porcelain", "--", "workers/extraction",
        ":!workers/extraction/experiments",
    )
    return {"git_commit": commit, "git_dirty": bool(status) if status is not None else None}


def gold_sha(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted([*directory.glob("*.json"), *directory.glob("text/*.txt")]):
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def format_table(records: list[dict[str, Any]]) -> str:
    if not records:
        return "No experiments yet."
    latest_gold = records[-1]["data"]["gold_sha"]
    header = (
        f"{'id':<5}{'name':<24}{'model':<28}{'prompt':<8}{'schema':<8}{'fs':>3} {'input':<12}"
        + "".join(f"{label:>8}" for _, label in TABLE_METRICS)
    )
    lines = [header]
    for r in records:
        c = r["config"]
        marker = "" if r["data"]["gold_sha"] == latest_gold else "  *other gold"
        lines.append(
            f"{r['id']:<5}{r['name'][:23]:<24}{str(c['llm_model'])[:27]:<28}"
            f"{c['prompt_version']:<8}{c['schema_version']:<8}{c['few_shot']:>3} {r['input']:<12}"
            + "".join(_cell(r["summary"].get(key), key) for key, _ in TABLE_METRICS)
            + marker
        )
    return "\n".join(lines)


def format_diff(previous: dict[str, Any], current: dict[str, Any]) -> str:
    lines = [f"vs {previous['id']} {previous['name']}:"]
    changed = [
        f"  {key}: {previous['config'].get(key)} -> {value}"
        for key, value in current["config"].items()
        if previous["config"].get(key) != value
    ]
    if previous["input"] != current["input"]:
        changed.append(f"  input: {previous['input']} -> {current['input']}")
    if previous["data"]["gold_sha"] != current["data"]["gold_sha"]:
        changed.append("  gold set changed – scores are not directly comparable")
    lines += changed or ["  config unchanged"]
    for key, value in current["summary"].items():
        before = previous["summary"].get(key)
        if value is None or before is None:
            continue
        delta = (value - before) * 100
        if abs(delta) >= 0.05:
            lines.append(f"  {key}: {before:.1%} -> {value:.1%} ({delta:+.1f} pp)")
    return "\n".join(lines)


def _cell(value: float | None, key: str) -> str:
    if value is None:
        return f"{'–':>8}"
    return f"{value:>8.1%}" if key == "ocr_cer" else f"{value:>8.0%}"


def _mean(values: Any) -> float | None:
    present = [v for v in values if v is not None]
    return round(mean(present), 2) if present else None


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
