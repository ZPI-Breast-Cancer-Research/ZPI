import { formatMetric } from "../format";
import { t, type MessageKey } from "../i18n";
import { anyFieldLabel } from "../review/fields";
import type { GateCheck } from "./api";

// gate rule codes from the backend → sentences in pl.ts; an unknown code shows as is.
// "whole": counts and percentage points, not a 0–1 score
const GATE_RULES: Record<string, { label: MessageKey; result: MessageKey; whole?: boolean }> = {
  dice_not_lower: { label: "models.gate.dice_not_lower", result: "models.gate.dice_not_lower.result" },
  no_large_drop: { label: "models.gate.no_large_drop", result: "models.gate.no_large_drop.result" },
  no_field_drop: { label: "models.gate.no_field_drop", result: "models.gate.no_field_drop.result", whole: true },
  failed_not_more: { label: "models.gate.failed_not_more", result: "models.gate.failed_not_more.result", whole: true },
};

export default function GateList({ gate }: { gate: GateCheck[] | null }) {
  if (!gate) return <p className="models__empty">{t("models.gate.pending")}</p>;
  const passed = gate.filter((check) => check.passed).length;
  return (
    <>
      <p className="models__label">{t("models.gate.title", { passed, n: gate.length })}</p>
      <ul className="gate">
        {gate.map((check) => {
          const rule = GATE_RULES[check.rule];
          const number = (n: number | null) => (n === null ? "—" : rule?.whole ? String(Math.round(n)) : formatMetric(n));
          const values = {
            threshold: number(check.threshold),
            value: number(check.value),
            baseline: number(check.baseline),
            study: check.studyNumber ?? "—",
            field: check.field ? anyFieldLabel(check.field) : "—",
          };
          return (
            <li key={check.rule}>
              {rule ? t(rule.label, values) : check.rule}
              <span className="gate__result">{rule && check.value !== null ? t(rule.result, values) : ""}</span>
              <span className={check.passed === null ? "status" : check.passed ? "status status--confirmed" : "status status--warning"}>
                {check.passed === null ? "—" : t(check.passed ? "models.gate.passed" : "models.gate.failed")}
              </span>
            </li>
          );
        })}
      </ul>
    </>
  );
}
