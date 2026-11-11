"""Text tables for the terminal: an evaluation ``Report`` and the experiment records.

Computes nothing itself.
"""

from typing import Any

from .report import SUMMARY_GROUPS, Report
from .scores import FieldScore

TABLE_METRICS = (
    ("field_accuracy", "fields"),
    ("zmiany_f1", "lesF1"),
    ("wezly_f1", "nodeF1"),
    ("wniosek_birads_accuracy", "birads"),
    ("ocr_cer", "CER"),
)


def format_report(report: Report) -> str:
    lines = []
    for p in report.provenance:
        lines.append(
            f"model: {p['llm_model'] or '?'} | prompt: {p['prompt_version']} | "
            f"schema: {p['schema_version']}"
        )
    skipped = ", ".join(
        f"{reason} {len(keys)} ({', '.join(keys)})" for reason, keys in report.skipped.items()
    )
    summary = f"documents: {len(report.evaluated)} evaluated"
    if report.errors:
        summary += f" (failed, scored as empty: {', '.join(report.errors)})"
    lines.append(summary + (f"; skipped: {skipped}" if skipped else ""))
    worst = report.ocr.worst
    if worst is not None:
        worst_key, worst_cer = worst
        lines.append(
            f"OCR character error rate: mean {report.ocr.mean:.1%}, "
            f"worst {worst_cer:.1%} ({worst_key})"
        )

    lines += ["", f"{'field group':<26}{'n':>5}{'acc':>7}{'P':>7}{'R':>7}{'F1':>7}"]
    for group in (None, *SUMMARY_GROUPS):
        lines.append(f"{group or 'all fields':<26}{_score_cells(report.group_score(group))}")
    birads = report.fields.get("wniosek.birads")
    if birads:
        lines.append(f"{'wniosek.birads':<26}{_score_cells(birads)}")

    lines += ["", f"{'entity':<14}{'gold':>6}{'pred':>6}{'match':>7}{'P':>7}{'R':>7}{'F1':>7}"]
    for name, e in report.entities.items():
        lines.append(
            f"{name:<14}{e.gold:>6}{e.predicted:>6}{e.matched:>7}"
            f"{_pct(e.precision)}{_pct(e.recall)}{_pct(e.f1)}"
        )

    width = max((len(name) for name in report.fields), default=10) + 2
    lines += [
        "",
        f"{'field':<{width}}{'n':>5}{'acc':>7}{'P':>7}{'R':>7}{'F1':>7}"
        f"{'wrong':>7}{'missed':>8}{'spurious':>10}",
    ]
    for name, s in sorted(report.fields.items()):
        lines.append(f"{name:<{width}}{_score_cells(s)}{s.wrong:>7}{s.missed:>8}{s.spurious:>10}")
    return "\n".join(lines)


def _score_cells(s: FieldScore) -> str:
    return f"{s.n:>5}{_pct(s.accuracy)}{_pct(s.precision)}{_pct(s.recall)}{_pct(s.f1)}"


def _pct(value: float | None) -> str:
    return f"{value:>7.0%}" if value is not None else f"{'–':>7}"


def format_experiments(records: list[dict[str, Any]]) -> str:
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
        # None: recorded from predictions that predate provenance.few_shot.
        few_shot = "?" if c["few_shot"] is None else c["few_shot"]
        lines.append(
            f"{r['id']:<5}{r['name'][:23]:<24}{str(c['llm_model'])[:27]:<28}"
            f"{c['prompt_version']:<8}{c['schema_version']:<8}{few_shot:>3} {r['input']:<12}"
            + "".join(_cell(r["summary"].get(key), key) for key, _ in TABLE_METRICS)
            + marker
        )
    return "\n".join(lines)


def format_experiment_diff(previous: dict[str, Any], current: dict[str, Any]) -> str:
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
