import WarningIcon from "../components/WarningIcon";
import { t } from "../i18n";
import type { Proposal } from "./api";
import { FIELDS, type FieldKey } from "./fields";

export type FieldState = "proposed" | "confirmed" | "corrected";

interface Props {
  proposals: Partial<Record<FieldKey, Proposal>>;
  values: Partial<Record<FieldKey, string>>;
  states: Partial<Record<FieldKey, FieldState>>;
  onChange: (key: FieldKey, value: string) => void;
  onConfirm: (key: FieldKey) => void;
}

export default function BiradsForm({ proposals, values, states, onChange, onConfirm }: Props) {
  return (
    <table className="birads">
      <thead>
        <tr>
          <th>{t("review.col.field")}</th>
          <th>{t("review.col.value")}</th>
          <th>{t("review.col.status")}</th>
        </tr>
      </thead>
      <tbody>
        {FIELDS.filter((f) => proposals[f.key]).map((field) => {
          const proposal = proposals[field.key]!;
          const state = states[field.key] ?? "proposed";
          const flagged = state === "proposed" && proposal.disagreement;
          const value = values[field.key] ?? "";
          const id = `field-${field.key}`;

          return (
            <tr key={field.key} className={`birads__row birads__row--${state}${flagged ? " birads__row--flag" : ""}`}>
              <td className="birads__label">
                {flagged && <WarningIcon label={t("review.field.check")} />}
                <label htmlFor={id}>{field.label}</label>
              </td>
              <td>
                {field.options ? (
                  <select id={id} className="select" value={value} onChange={(event) => onChange(field.key, event.target.value)}>
                    {field.options.map((option) => (
                      <option key={option} value={option}>
                        {option}
                        {option === proposal.value ? ` · ${t("review.field.model")}` : ""}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="birads__num">
                    <input
                      id={id}
                      className="input"
                      inputMode="decimal"
                      value={value}
                      onChange={(event) => onChange(field.key, event.target.value.replace(",", "."))}
                    />
                    <span className="muted">{field.unit}</span>
                  </span>
                )}
                {flagged && <p className="birads__note">{t("review.field.disagree")}</p>}
              </td>
              <td className="birads__status">
                {state === "proposed" ? (
                  <>
                    <span className={flagged ? "status status--warning" : "status"}>
                      {t(flagged ? "review.field.check" : "review.field.proposed")}
                    </span>
                    <button type="button" className="btn btn--small" onClick={() => onConfirm(field.key)}>
                      {t("review.field.confirm")}
                    </button>
                  </>
                ) : (
                  <span className={state === "corrected" ? "status status--corrected" : "status status--confirmed"}>
                    {t(state === "corrected" ? "review.field.corrected" : "review.field.confirmed")}
                  </span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
