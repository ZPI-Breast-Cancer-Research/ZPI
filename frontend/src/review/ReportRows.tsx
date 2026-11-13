import { useState, type FocusEvent, type KeyboardEvent, type ReactNode } from "react";

import Select from "../components/Select";
import { t } from "../i18n";
import type { Extraction, WireMeasure, WireQualifier, WireSide, WireSize } from "./extraction";
import { areaOfClock, FROM_WIRE, lesionType, type LesionType } from "./report";
import {
  getAt,
  hiddenRows,
  QUALIFIERS,
  qualifierLabel,
  readList,
  readMeasure,
  readSize,
  rowLines,
  rowState,
  validClock,
  validNumber,
  visibleRows,
  writeType,
  type Answers,
  type Group,
  type Line,
  type Row,
  type RowState,
} from "./rows";

export interface Section {
  group: Group;
  // the lesion's own fields go without a band
  band: boolean;
}

interface Props {
  sections: Section[];
  original: Extraction;
  current: Extraction;
  answers: Answers;
  // the lesion's side, for the area of a clock position
  side: WireSide | null;
  // new values for the row's paths (null keeps them); confirm marks them checked
  onAnswer: (row: Row, values: unknown[] | null, confirm: boolean) => void;
  onRestore: (row: Row) => void;
  onAdd: (row: Row) => void;
}

const CATEGORIES: LesionType[] = ["mass", "distortion", "calcifications", "cyst", "other"];
const BOOLS = ["true", "false"];
export const rowId = (row: Row) => `row-${row.key.replace(/\./g, "-")}`;

// the next field that waits, after this one
function focusNext(after: string) {
  requestAnimationFrame(() => {
    const rows = [...document.querySelectorAll<HTMLElement>(".rows__row--todo")];
    const here = document.getElementById(after);
    const next = rows.find((r) => here && here.compareDocumentPosition(r) & Node.DOCUMENT_POSITION_FOLLOWING) ?? rows[0];
    next?.querySelector<HTMLElement>("input, button")?.focus();
  });
}

export default function ReportRows({ sections, original, current, answers, side, onAnswer, onRestore, onAdd }: Props) {
  // a checked row opened again to change it
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState<string | null>(null);

  return (
    <div className="rows">
      {sections.map(({ group, band }) => {
        const shown = visibleRows(group, original, current, answers.added);
        const hidden = hiddenRows(group, original, current, answers.added);
        const done = shown.filter((r) => rowState(r, original, current, answers.confirmed) !== "todo").length;
        return (
          <section key={group.key} className="rows__group">
            {band && (
              <h3 className="rows__band">
                {group.title}
                <span>{done === shown.length ? t("rows.checked") : t("rows.checkedOf", { n: done, total: shown.length })}</span>
              </h3>
            )}
            {shown.map((row) => (
              <RowView
                key={row.key}
                row={row}
                state={rowState(row, original, current, answers.confirmed)}
                original={original}
                current={current}
                side={side}
                editing={editing === row.key}
                onEdit={(open) => setEditing(open ? row.key : null)}
                onAnswer={(values, confirm) => onAnswer(row, values, confirm)}
                onRestore={() => onRestore(row)}
              />
            ))}
            {hidden.length > 0 && (
              <div className="rows__add">
                {adding === group.key ? (
                  hidden.map((row) => (
                    <button
                      key={row.key}
                      type="button"
                      className="link"
                      onClick={() => {
                        setAdding(null);
                        onAdd(row);
                        requestAnimationFrame(() => document.getElementById(rowId(row))?.querySelector<HTMLElement>("input, button")?.focus());
                      }}
                    >
                      + {row.label}
                    </button>
                  ))
                ) : (
                  <button type="button" className="link" onClick={() => setAdding(group.key)}>
                    + {t("rows.other")}
                  </button>
                )}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

interface RowProps {
  row: Row;
  state: RowState;
  original: Extraction;
  current: Extraction;
  side: WireSide | null;
  editing: boolean;
  onEdit: (open: boolean) => void;
  onAnswer: (values: unknown[] | null, confirm: boolean) => void;
  onRestore: () => void;
}

function RowView({ row, state, original, current, side, editing, onEdit, onAnswer, onRestore }: RowProps) {
  const id = rowId(row);
  // two controls in one row (both breasts, a node's region and side) wait as text and open on a click
  const pair = row.perSide || row.kind.type === "where";
  const open = (state === "todo" && !pair) || editing;
  const values = row.paths.map((p) => getAt(current, p));
  const note = state === "todo" ? (row.note?.(current) ?? null) : null;

  if (!open) {
    const model = state === "corrected" ? linesText(rowLines(row, original, side)) : null;
    return (
      <div id={id} className={`rows__row rows__row--${state}`} onClick={() => onEdit(true)}>
        <span className="rows__label">{row.label}</span>
        <div className="rows__value">
          {rowLines(row, current, side).map((line, i) => (
            <div key={i} className="rows__text">
              <LineText line={line} />
            </div>
          ))}
          {model !== null && <div className="rows__model">{t("rows.model", { v: model })}</div>}
        </div>
        <div className="rows__act">
          {state === "todo" ? (
            <button
              type="button"
              className="btn rows__confirm"
              onClick={(event) => {
                event.stopPropagation();
                onAnswer(null, true);
                focusNext(id);
              }}
            >
              {t("rows.confirm")}
            </button>
          ) : state === "corrected" ? (
            <button
              type="button"
              className="link"
              onClick={(event) => {
                event.stopPropagation();
                onRestore();
              }}
            >
              {t("rows.restore")}
            </button>
          ) : (
            <button type="button" className="rows__change">
              {t("rows.change")}
            </button>
          )}
        </div>
      </div>
    );
  }

  const close = () => {
    onEdit(false);
    focusNext(id);
  };
  return (
    <Editor
      key={`${row.key}|${JSON.stringify(values)}`}
      id={id}
      row={row}
      values={values}
      side={side}
      note={note}
      state={state}
      onAnswer={(next, confirm) => {
        onAnswer(next, confirm);
        if (confirm) close();
      }}
      onLeave={() => onEdit(false)}
      onCancel={() => onEdit(false)}
    />
  );
}

function LineText({ line }: { line: Line }) {
  return (
    <>
      {line.text ?? <span className="rows__none">{t("row.empty")}</span>}
      {line.extra && <span className="rows__extra"> · {line.extra}</span>}
    </>
  );
}

const linesText = (lines: Line[]) => lines.map((l) => [l.text ?? t("row.empty"), l.extra].filter(Boolean).join(" · ")).join("; ");

interface EditorProps {
  id: string;
  row: Row;
  values: unknown[];
  side: WireSide | null;
  note: { text: string; emphasis: string } | null;
  state: RowState;
  onAnswer: (values: unknown[] | null, confirm: boolean) => void;
  onLeave: () => void;
  onCancel: () => void;
}

// what the inputs hold while typing
function draftOf(row: Row, values: unknown[]): string[] {
  const kind = row.kind.type;
  if (kind === "text") return values.map((v) => (v as string | null) ?? "");
  if (kind === "list") return [((values[0] as string[] | null) ?? []).join(", ")];
  if (kind === "measure") return [String((values[0] as WireMeasure | null)?.wartosc ?? "")];
  if (kind === "size") {
    const size = values[0] as WireSize | null;
    const numbers = (size?.wartosci ?? []).map(String);
    return [size?.kwalifikator ?? "dokładny", ...Array.from({ length: Math.max(2, numbers.length) }, (_, i) => numbers[i] ?? "")];
  }
  if (kind === "place") return [(values[0] as string | null) ?? "", String((values[1] as WireMeasure | null)?.wartosc ?? "")];
  if (kind === "where") return [(values[0] as string | null) ?? "", (values[1] as string | null) ?? ""];
  return [];
}

// back in the worker's shape, or null when something can't be read
function valuesOf(row: Row, draft: string[], previous: unknown[]): unknown[] | null {
  const kind = row.kind;
  if (kind.type === "text") return draft.map((d) => d.trim() || null);
  if (kind.type === "list") return [readList(draft[0])];
  if (kind.type === "measure") {
    if (!validNumber(draft[0])) return null;
    return [readMeasure(draft[0], (previous[0] as WireMeasure | null)?.jednostka ?? kind.unit)];
  }
  if (kind.type === "size") {
    const [qualifier, ...numbers] = draft;
    if (!numbers.every(validNumber)) return null;
    return [readSize(numbers, qualifier as WireQualifier, (previous[0] as WireSize | null)?.jednostka ?? "mm")];
  }
  if (kind.type === "place") {
    if (!validClock(draft[0]) || !validNumber(draft[1])) return null;
    return [draft[0].trim() || null, readMeasure(draft[1], (previous[1] as WireMeasure | null)?.jednostka ?? "cm")];
  }
  if (kind.type === "where") return [draft[0].trim() || null, draft[1] || null];
  return null;
}

function errorOf(row: Row, draft: string[]): string | null {
  const kind = row.kind.type;
  if (kind === "place" && !validClock(draft[0])) return t("rows.badClock");
  const numbers = kind === "size" ? draft.slice(1) : kind === "place" ? [draft[1]] : kind === "measure" ? [draft[0]] : [];
  return numbers.every(validNumber) ? null : t("rows.badNumber");
}

function Editor({ id, row, values, side, note, state, onAnswer, onLeave, onCancel }: EditorProps) {
  const [draft, setDraft] = useState(() => draftOf(row, values));
  const typed = draft.length > 0;
  const error = typed ? errorOf(row, draft) : null;
  const set = (i: number, value: string) => setDraft((d) => d.map((x, j) => (j === i ? value : x)));
  const changed = typed && JSON.stringify(valuesOf(row, draft, values)) !== JSON.stringify(values.map((v) => v ?? null));

  const confirm = () => {
    if (!typed) return onAnswer(null, true);
    const next = valuesOf(row, draft, values);
    if (next) onAnswer(next, true);
  };
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Enter" && (event.target as HTMLElement).tagName === "INPUT") {
      event.preventDefault();
      confirm();
    }
    if (event.key === "Escape") onCancel();
  };
  // leaving the row keeps a change without confirming it
  const onBlur = (event: FocusEvent) => {
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
    const next = typed && changed ? valuesOf(row, draft, values) : null;
    if (next) onAnswer(next, false);
    onLeave();
  };

  return (
    <div id={id} className={`rows__row rows__row--todo rows__row--open${state !== "todo" ? " rows__row--again" : ""}`} onKeyDown={onKeyDown} onBlur={onBlur}>
      <label className="rows__label" htmlFor={`${id}-${row.kind.type === "size" ? "q" : 0}`}>
        {row.label}
      </label>
      <div className="rows__value">
        <div className="rows__controls">
          <Controls id={id} row={row} values={values} draft={draft} set={set} side={side} error={!!error} again={state !== "todo"} onPick={(v) => onAnswer(v, true)} />
        </div>
        {error && <div className="rows__error">{error}</div>}
        {!error && note && (
          <div className="rows__note">
            {note.text} · <em>{note.emphasis}</em>
          </div>
        )}
      </div>
      <div className="rows__act">
        <button type="button" className="btn rows__confirm" aria-disabled={!!error} onClick={() => !error && confirm()}>
          {t("rows.confirm")}
        </button>
      </div>
    </div>
  );
}

interface ControlsProps {
  id: string;
  row: Row;
  values: unknown[];
  draft: string[];
  set: (i: number, value: string) => void;
  side: WireSide | null;
  error: boolean;
  // opened again from its text: a list opens at once
  again: boolean;
  // a picked option answers the row at once
  onPick: (values: unknown[]) => void;
}

function Controls({ id, row, values, draft, set, side, error, again, onPick }: ControlsProps): ReactNode {
  const kind = row.kind;
  const input = (i: number, width: number, label: string) => (
    <input
      id={`${id}-${i}`}
      className={error ? "input rows__input rows__input--error" : "input rows__input"}
      style={{ width }}
      aria-label={label}
      value={draft[i]}
      onChange={(event) => set(i, event.target.value)}
    />
  );
  const unit = (text: string) => <span className="rows__unit">{text}</span>;
  const narrow = row.kind.type === "choice" && row.kind.options.every((o) => o.length <= 2);
  const choice = (i: number, value: string, options: readonly string[], label: (v: string) => string, pick: (v: string) => void) => (
    <Select
      id={`${id}-${i}`}
      className={narrow ? "rows__select rows__select--narrow" : "rows__select"}
      value={value}
      options={["", ...options]}
      label={(v) => (v ? label(v) : t("row.empty"))}
      placeholder={t("row.empty")}
      ariaLabel={row.label}
      startOpen={again && i === 0 && !row.perSide}
      onChange={pick}
    />
  );
  // the two breasts: one list each, answered together
  const pair = (render: (i: number, value: unknown, pick: (v: unknown) => void) => ReactNode) => (
    <div className="rows__pair">
      {(["prawa", "lewa"] as const).map((breast) => {
        const i = breast === "lewa" ? 0 : 1;
        return (
          <span key={breast} className="rows__side">
            <span className="rows__unit">{t(`field.side.${FROM_WIRE.side[breast]}`).toLowerCase()}</span>
            {render(i, values[i], (v) => onPick(values.map((old, j) => (j === i ? v : old))))}
          </span>
        );
      })}
    </div>
  );

  switch (kind.type) {
    case "choice":
      return choice(0, (values[0] as string | null) ?? "", kind.options, kind.label ?? ((v) => v), (v) => onPick([v || null]));
    case "lesionType":
      return choice(
        0,
        lesionType(values[0] as string | null) ?? "",
        CATEGORIES,
        (v) => t(`field.type.${v as LesionType}`),
        (v) => onPick([writeType(v, values[0] as string | null)]),
      );
    case "bool":
      if (row.perSide) return pair((i, value, pick) => choice(i, value === null || value === undefined ? "" : String(value), BOOLS, (v) => t(v === "true" ? "row.yes" : "row.no"), (v) => pick(v ? v === "true" : null)));
      return choice(0, values[0] === null || values[0] === undefined ? "" : String(values[0]), BOOLS, (v) => t(v === "true" ? "row.yes" : "row.no"), (v) => onPick([v ? v === "true" : null]));
    case "text":
      if (row.perSide)
        return (
          <div className="rows__pair">
            <span className="rows__side">
              {unit(t("field.side.right").toLowerCase())}
              {input(1, 150, row.label)}
            </span>
            <span className="rows__side">
              {unit(t("field.side.left").toLowerCase())}
              {input(0, 150, row.label)}
            </span>
          </div>
        );
      return input(0, 230, row.label);
    case "list":
      return input(0, 230, row.label);
    case "measure":
      return (
        <>
          {input(0, 56, row.label)}
          {unit((values[0] as WireMeasure | null)?.jednostka ?? kind.unit)}
        </>
      );
    case "size":
      return (
        <>
          <Select
            id={`${id}-q`}
            className="rows__select rows__select--qualifier"
            value={draft[0]}
            options={QUALIFIERS}
            label={(q) => qualifierLabel(q as WireQualifier)}
            ariaLabel={t("rows.qualifier")}
            onChange={(q) => set(0, q)}
          />
          {draft.slice(1).map((_, k) => (
            <span key={k} className="rows__dim">
              {k > 0 && unit("×")}
              {input(k + 1, 36, row.label)}
            </span>
          ))}
          {unit((values[0] as WireSize | null)?.jednostka ?? "mm")}
        </>
      );
    case "place": {
      const area = side ? areaOfClock(draft[0], FROM_WIRE.side[side], validNumber(draft[1]) && draft[1].trim() ? { value: Number(draft[1].replace(",", ".")), unit: "cm" } : null) : null;
      return (
        <>
          {input(0, 54, t("row.clock"))}
          {unit(t("rows.clockUnit"))}
          {input(1, 44, t("row.fromNipple"))}
          {unit((values[1] as WireMeasure | null)?.jednostka ?? "cm")}
          {area && unit(`· ${t(`field.quadrant.${area}`)}`)}
        </>
      );
    }
    case "where":
      return (
        <>
          {input(0, 118, row.label)}
          {choice(1, draft[1], ["lewa", "prawa", "obustronnie"], (v) => t(`field.side.${FROM_WIRE.side[v as WireSide]}`).toLowerCase(), (v) => set(1, v))}
        </>
      );
  }
}

