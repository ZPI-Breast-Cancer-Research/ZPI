import { useEffect, useRef, useState, type FocusEvent, type KeyboardEvent, type MutableRefObject } from "react";

import Hint from "../components/Hint";
import Select from "../components/Select";
import WarningIcon from "../components/WarningIcon";
import { t } from "../i18n";
import { disagree, formatValue, getAt, isEmpty, pathKey, type Cell, type DetailGroup, type DetailRow, type Kind, type Path } from "./details";
import { WIRE_QUALIFIERS, WIRE_UNITS, type Extraction, type WireMeasure, type WireSize } from "./extraction";

interface Props {
  title: string;
  groups: DetailGroup[];
  // the report with every answer so far, and as the model gave it
  current: Extraction;
  original: Extraction;
  confirmed: boolean;
  // the model guessed that these observations are one lesion
  linkWarning?: string | null;
  onEdit: (path: Path, value: unknown) => void;
  onConfirm: (confirmed: boolean) => void;
}

interface Line {
  cells: Cell[];
  value: unknown;
  tags: string[];
}

// one value for cells that agree, one line each when they don't
function linesOf(row: DetailRow, values: unknown[]): Line[] {
  const present = row.cells.map((cell, i) => ({ cell, value: values[i] })).filter((c) => !isEmpty(c.value));
  if (!present.length) return [{ cells: row.cells, value: null, tags: [] }];
  const tag = (cells: Cell[]) => cells.map((c) => c.tag).filter((x): x is string => !!x);
  if (new Set(present.map((c) => JSON.stringify(c.value))).size === 1) {
    const cells = present.map((c) => c.cell);
    return [{ cells, value: present[0].value, tags: tag(cells) }];
  }
  return present.map((c) => ({ cells: [c.cell], value: c.value, tags: tag([c.cell]) }));
}

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

export default function ReportDetails({ title, groups, current, original, confirmed, linkWarning, onEdit, onConfirm }: Props) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);

  const row = (r: DetailRow, group: string) => {
    const id = `${group}.${r.key}`;
    const values = r.cells.map((c) => getAt(current, c.path));
    const corrected = r.cells.some((c) => !same(getAt(current, c.path), getAt(original, c.path)));
    const warn = !!r.compare && disagree(r.kind, values);
    return (
      <tr key={r.key} className={corrected ? "details__row details__row--corrected" : "details__row"}>
        <th>
          {warn && <WarningIcon label={t("detail.disagree")} />}
          {r.label}
        </th>
        <td>
          {editing === id ? (
            <EditRow row={r} values={values} onEdit={onEdit} onClose={() => setEditing(null)} />
          ) : (
            linesOf(r, values).map((line) => (
              <div key={pathKey(line.cells[0].path)} className="details__line">
                <button type="button" className={isEmpty(line.value) ? "details__value details__value--empty" : "details__value"} onClick={() => setEditing(id)}>
                  {formatValue(r.kind, line.value)}
                </button>
                {line.tags.length > 0 && <span className="details__tag">{line.tags.join(", ")}</span>}
              </div>
            ))
          )}
        </td>
        <td className="details__status">{corrected && <span className="status status--corrected">{t("review.field.corrected")}</span>}</td>
      </tr>
    );
  };

  return (
    <section className="details">
      <div className="details__head">
        <button type="button" className="details__toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <span className={open ? "details__chevron details__chevron--open" : "details__chevron"} aria-hidden="true" />
          {title}
        </button>
        {linkWarning && (
          <Hint name={t("detail.linked")} text={linkWarning} place="top">
            <span className="details__link">
              <WarningIcon label={t("detail.linked")} />
            </span>
          </Hint>
        )}
        {confirmed ? (
          <span className="details__confirmed">
            <span className="status status--confirmed">{t("detail.agrees")}</span>
            <button type="button" className="btn btn--small" onClick={() => onConfirm(false)}>
              {t("detail.undo")}
            </button>
          </span>
        ) : (
          <button type="button" className="btn btn--small" onClick={() => onConfirm(true)}>
            {t("detail.agrees")}
          </button>
        )}
      </div>
      {open &&
        groups.map((group) => (
          <div key={group.key}>
            {group.title && <p className="details__group">{group.title}</p>}
            <table className="details__table">
              <tbody>{group.rows.map((r) => row(r, group.key))}</tbody>
            </table>
          </div>
        ))}
    </section>
  );
}

// one field per observation
function EditRow({ row, values, onEdit, onClose }: { row: DetailRow; values: unknown[]; onEdit: Props["onEdit"]; onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  const cancelled = useRef(false);
  const single = row.cells.length === 1;

  useEffect(() => {
    if (!single) box.current?.querySelector<HTMLElement>("input, button")?.focus();
  }, [single]);

  return (
    <div
      ref={box}
      className="details__editing"
      onBlur={(event: FocusEvent) => !event.currentTarget.contains(event.relatedTarget as Node | null) && onClose()}
      onKeyDown={(event: KeyboardEvent) => {
        if (event.key === "Enter") onClose();
        if (event.key === "Escape") {
          event.stopPropagation();
          cancelled.current = true;
          onClose();
        }
      }}
    >
      {row.cells.map((cell, i) => (
        <div key={pathKey(cell.path)} className="details__line">
          {!single && cell.tag && <span className="details__tag details__tag--lead">{cell.tag}</span>}
          <Editor
            id={`detail-${pathKey(cell.path)}`}
            kind={row.kind}
            value={values[i]}
            label={[row.label, cell.tag].filter(Boolean).join(" ")}
            single={single}
            cancelled={cancelled}
            onCommit={(value) => onEdit(cell.path, value)}
            onDone={onClose}
          />
        </div>
      ))}
    </div>
  );
}

const BOOL = ["", "yes", "no"];
const toBool = (v: string) => (v === "yes" ? true : v === "no" ? false : null);
const fromBool = (v: unknown) => (v === true ? "yes" : v === false ? "no" : "");
const number = (text: string) => {
  const n = Number(text.replace(",", "."));
  return text.trim() && Number.isFinite(n) ? n : null;
};

interface EditorProps {
  id: string;
  kind: Kind;
  value: unknown;
  label: string;
  // alone in its row: the list opens at once
  single: boolean;
  cancelled: MutableRefObject<boolean>;
  onCommit: (value: unknown) => void;
  onDone: () => void;
}

function Editor({ id, kind, value, label, single, cancelled, onCommit, onDone }: EditorProps) {
  const measure = (value as WireMeasure | null) ?? null;
  const size = (value as WireSize | null) ?? null;
  const [text, setText] = useState(() =>
    kind === "list"
      ? ((value as string[] | null) ?? []).join(", ")
      : kind === "measure"
        ? measure
          ? String(measure.wartosc)
          : ""
        : kind === "size"
          ? size
            ? size.wartosci.join("×")
            : ""
          : typeof value === "string"
            ? value
            : "",
  );
  const [unit, setUnit] = useState<string>(measure?.jednostka ?? size?.jednostka ?? "mm");
  const [qualifier, setQualifier] = useState<string>(size?.kwalifikator ?? "dokładny");

  const parsed = () => {
    if (kind === "list") return text.split(",").map((s) => s.trim()).filter(Boolean);
    if (kind === "measure") return number(text) === null ? null : { wartosc: number(text), jednostka: unit };
    if (kind === "size") {
      const values = text.split(/[x×*]/i).map(number);
      return !text.trim() || values.some((v) => v === null) ? null : { wartosci: values, jednostka: unit, kwalifikator: qualifier };
    }
    return text.trim() || null;
  };
  const keep = () => !cancelled.current && onCommit(parsed());

  if (Array.isArray(kind) || kind === "bool") {
    const options = kind === "bool" ? BOOL : ["", ...(kind as readonly string[])];
    return (
      <Select
        id={id}
        className="details__edit"
        startOpen={single}
        value={kind === "bool" ? fromBool(value) : ((value as string | null) ?? "")}
        options={options}
        ariaLabel={label}
        label={(v) => (!v ? "—" : kind === "bool" ? t(v === "yes" ? "detail.yes" : "detail.no") : v)}
        onChange={(v) => {
          onCommit(kind === "bool" ? toBool(v) : v || null);
          if (single) onDone();
        }}
      />
    );
  }
  return (
    <span
      className="details__editor"
      onBlur={(event: FocusEvent) => !event.currentTarget.contains(event.relatedTarget as Node | null) && keep()}
      onKeyDown={(event: KeyboardEvent) => event.key === "Enter" && keep()}
    >
      <input id={id} className="input" aria-label={label} value={text} autoFocus={single} onChange={(event) => setText(event.target.value)} />
      {(kind === "measure" || kind === "size") && <Select id={`${id}-unit`} className="details__unit" value={unit} options={WIRE_UNITS} ariaLabel={label} onChange={setUnit} />}
      {kind === "size" && (
        <Select id={`${id}-qualifier`} className="details__unit" value={qualifier} options={WIRE_QUALIFIERS} ariaLabel={label} onChange={setQualifier} />
      )}
    </span>
  );
}
