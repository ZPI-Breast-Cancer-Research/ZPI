import { useState } from "react";

import Select from "../components/Select";
import WarningIcon from "../components/WarningIcon";
import { t } from "../i18n";
import { fieldLabel, FIELDS, optionLabel, type FieldDef, type FieldKey, type Proposals, type Values } from "./fields";

export type FieldState = "proposed" | "confirmed" | "corrected";

interface Props {
  keys: FieldKey[];
  proposals: Proposals;
  values: Values;
  states: Partial<Record<FieldKey, FieldState>>;
  onChange: (key: FieldKey, value: string) => void;
  onConfirm: (keys: FieldKey[]) => void;
  // the mask's longest side, under the size
  maskSizeMm?: number | null;
}

// a row waits while any of its fields does
function rowState(keys: FieldKey[], states: Props["states"]): FieldState {
  const all = keys.map((key) => states[key] ?? "proposed");
  return all.includes("proposed") ? "proposed" : all.includes("corrected") ? "corrected" : "confirmed";
}

export default function BiradsForm({ keys, proposals, values, states, onChange, onConfirm, maskSizeMm }: Props) {
  const rows = FIELDS.filter((f) => !f.row && keys.includes(f.key)).map((main) => [main, ...FIELDS.filter((f) => f.row === main.key && keys.includes(f.key))]);

  const control = (field: FieldDef) => {
    const id = `field-${field.key}`;
    const value = values[field.key] ?? "";
    const narrow = field.narrow ? " birads__control--narrow" : "";
    if (field.options) {
      return (
        <Select
          key={field.key}
          id={id}
          className={`birads__control${narrow}`}
          value={value}
          options={field.options}
          mark={{ value: proposals[field.key]!.value, text: t("review.field.model") }}
          label={(code) => optionLabel(field.key, code)}
          ariaLabel={fieldLabel(field.key)}
          onChange={(next) => onChange(field.key, next)}
        />
      );
    }
    return (
      <span key={field.key} className={`birads__control birads__num${narrow}`}>
        <NumberInput id={id} label={fieldLabel(field.key)} value={value} onChange={(next) => onChange(field.key, next)} />
        <span className="muted">{field.unit}</span>
      </span>
    );
  };

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
        {rows.map((fields) => {
          const main = fields[0];
          const rowKeys = fields.map((f) => f.key);
          const state = rowState(rowKeys, states);
          const check = fields.map((f) => proposals[f.key]?.check).find(Boolean);
          const flagged = state === "proposed" && !!check;
          const hints = fields.flatMap((f) => proposals[f.key]?.hints ?? []);

          return (
            <tr key={main.key} className={`birads__row birads__row--${state}${flagged ? " birads__row--flag" : ""}`}>
              <td className="birads__label">
                {flagged && <WarningIcon label={t("review.field.check")} />}
                <label htmlFor={`field-${main.key}`}>{fieldLabel(main.key)}</label>
              </td>
              <td>
                <div className="birads__controls">{fields.map(control)}</div>
                {main.key === "size" && maskSizeMm != null && (
                  <p
                    className={Math.abs(maskSizeMm - Number(values.size)) >= 3 ? "birads__mask birads__mask--off" : "birads__mask"}
                    title={t("review.field.fromMaskTitle")}
                  >
                    {t("review.field.fromMask", { n: Math.round(maskSizeMm) })}
                  </p>
                )}
                {hints.map((hint) => (
                  <p key={hint} className="birads__mask">
                    {hint}
                  </p>
                ))}
                {flagged && <p className="birads__note">{check}</p>}
              </td>
              <td className="birads__status">
                {state === "proposed" ? (
                  <>
                    <span className={flagged ? "status status--warning" : "status"}>{t(flagged ? "review.field.check" : "review.field.proposed")}</span>
                    <button type="button" className="btn btn--small" onClick={() => onConfirm(rowKeys)}>
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

// "4." stays on screen on the way to "4.5"
function NumberInput({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (value: string) => void }) {
  const [typing, setTyping] = useState<string | null>(null);
  return (
    <input
      id={id}
      className="input"
      inputMode="decimal"
      aria-label={label}
      value={typing ?? value}
      onFocus={() => setTyping(value)}
      onBlur={() => setTyping(null)}
      onChange={(event) => {
        const next = event.target.value.replace(",", ".");
        setTyping(next);
        if (!next.trim() || Number.isFinite(Number(next))) onChange(next);
      }}
    />
  );
}
