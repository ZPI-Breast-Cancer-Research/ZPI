import Select from "../components/Select";
import WarningIcon from "../components/WarningIcon";
import { t } from "../i18n";
import { fieldLabel, FIELDS, optionLabel, type FieldKey, type Proposals } from "./fields";

export type FieldState = "proposed" | "confirmed" | "corrected";

interface Props {
  proposals: Proposals;
  values: Partial<Record<FieldKey, string>>;
  states: Partial<Record<FieldKey, FieldState>>;
  onChange: (key: FieldKey, value: string) => void;
  onConfirm: (key: FieldKey) => void;
  // the mask's own size, shown under Wymiar to compare with the report
  maskSizeMm?: number | null;
}

export default function BiradsForm({ proposals, values, states, onChange, onConfirm, maskSizeMm }: Props) {
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
          const flagged = state === "proposed" && !!proposal.check;
          const value = values[field.key] ?? "";
          const id = `field-${field.key}`;

          return (
            <tr key={field.key} className={`birads__row birads__row--${state}${flagged ? " birads__row--flag" : ""}`}>
              <td className="birads__label">
                {flagged && <WarningIcon label={t("review.field.check")} />}
                <label htmlFor={id}>{fieldLabel(field.key)}</label>
              </td>
              <td>
                {field.options ? (
                  <Select
                    id={id}
                    value={value}
                    options={field.options}
                    mark={{ value: proposal.value, text: t("review.field.model") }}
                    label={(code) => optionLabel(field.key, code)}
                    onChange={(next) => onChange(field.key, next)}
                  />
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
                {field.key === "size" && maskSizeMm != null && (
                  <p
                    className={Math.abs(maskSizeMm - Number(value)) >= 3 ? "birads__mask birads__mask--off" : "birads__mask"}
                    title={t("review.field.fromMaskTitle")}
                  >
                    {t("review.field.fromMask", { n: Math.round(maskSizeMm) })}
                  </p>
                )}
                {proposal.hints?.map((hint) => (
                  <p key={hint} className="birads__mask">
                    {hint}
                  </p>
                ))}
                {flagged && <p className="birads__note">{proposal.check}</p>}
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
