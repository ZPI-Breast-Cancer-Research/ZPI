import type { ReportPart } from "./api";
import type { FieldState } from "./BiradsForm";
import type { FieldKey } from "./fields";

export default function ReportText({ parts, states }: { parts: ReportPart[]; states: Partial<Record<FieldKey, FieldState>> }) {
  return (
    <p className="report-text">
      {parts.map((part, i) =>
        part.field ? (
          <mark key={i} className={`report-text__mark report-text__mark--${states[part.field] ?? "proposed"}`}>
            {part.text}
          </mark>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </p>
  );
}
