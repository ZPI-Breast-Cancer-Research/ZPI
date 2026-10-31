from .scores import SUMMARY_GROUPS, FieldScore, Report


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
    if report.ocr_cer:
        worst = max(report.ocr_cer, key=report.ocr_cer.__getitem__)
        lines.append(
            f"OCR character error rate: mean {report.mean_ocr_cer:.1%}, "
            f"worst {report.ocr_cer[worst]:.1%} ({worst})"
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
