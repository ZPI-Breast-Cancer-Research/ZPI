import { formatNumber } from "../format";
import { t, type MessageKey } from "../i18n";
import {
  WIRE_BIRADS,
  WIRE_COUNTS,
  WIRE_ECHOES,
  WIRE_HOMOGENEITY,
  WIRE_MARGINS,
  WIRE_SHAPES,
  type Extraction,
  type WireMeasure,
  type WireModality,
  type WireSide,
  type WireSize,
} from "./extraction";
import { largestMm, measureOfWire, sizeOfWire } from "./report";
import { measureText, sizeText } from "./fields";

// fields outside the short form, by their path in the worker's JSON

export type Path = (string | number)[];
export const pathKey = (path: Path) => path.join(".");
const pathOf = (key: string): Path => key.split(".").map((step) => (/^\d+$/.test(step) ? Number(step) : step));

export type Kind = "text" | "list" | "bool" | "measure" | "size" | "fixed" | readonly string[];

export interface Cell {
  // which observation or breast the value belongs to
  tag: string | null;
  path: Path;
}

export interface DetailRow {
  key: string;
  label: string;
  kind: Kind;
  cells: Cell[];
  // MG and USG should agree
  compare?: boolean;
  // "obie" when both breasts agree
  allTag?: string;
  // a warning, from the report as it reads now
  check?: (current: Extraction) => string | null;
}

export interface DetailGroup {
  key: string;
  title: string | null;
  rows: DetailRow[];
}

export type Edits = Record<string, unknown>;

// changed values by path, fields confirmed in the form, sections that agree with the report
export interface Details {
  edits: Edits;
  confirmed: string[];
  agreed: string[];
}

export const NO_DETAILS: Details = { edits: {}, confirmed: [], agreed: [] };

export type FieldCheck = "confirmed" | "corrected" | "unverified";

// changed, confirmed (in the form or a whole section) or neither
export function fieldChecks(original: Extraction, current: Extraction, confirmed: Set<string>, sections: { rows: DetailRow[]; agreed: boolean }[]): Record<string, FieldCheck> {
  const agreed = new Set(sections.flatMap((s) => (s.agreed ? s.rows.flatMap((r) => r.cells.map((c) => pathKey(c.path))) : [])));
  const paths = new Map<string, Path>();
  for (const cell of sections.flatMap((s) => s.rows.flatMap((r) => r.cells))) paths.set(pathKey(cell.path), cell.path);
  for (const key of confirmed) paths.set(key, pathOf(key));
  const checks: Record<string, FieldCheck> = {};
  for (const [key, path] of paths) {
    const changed = JSON.stringify(getAt(current, path) ?? null) !== JSON.stringify(getAt(original, path) ?? null);
    checks[key] = changed ? "corrected" : confirmed.has(key) || agreed.has(key) ? "confirmed" : "unverified";
  }
  return checks;
}

export function getAt(data: unknown, path: Path): unknown {
  return path.reduce<unknown>((node, step) => (node == null ? undefined : (node as Record<string | number, unknown>)[step]), data);
}

function setAt(data: unknown, path: Path, value: unknown) {
  const parent = getAt(data, path.slice(0, -1)) as Record<string | number, unknown> | undefined;
  if (parent) parent[path[path.length - 1]] = value;
}

export function applyDetails(data: Extraction, edits: Edits): Extraction {
  const copy: Extraction = structuredClone(data);
  for (const [key, value] of Object.entries(edits)) setAt(copy, pathOf(key), value);
  return copy;
}

const label = (key: string) => t(`detail.${key}` as MessageKey);
const modality = (m: WireModality) => t(`modality.${m === "usg" ? "ultrasound" : "mammography"}`);
const SIDES: Record<WireSide, string> = { lewa: "left", prawa: "right", obustronnie: "both" };

export function lesionRows(data: Extraction, index: number): DetailRow[] {
  const obs = data.zmiany[index].obserwacje;
  // depth, echogenicity and homogeneity are ultrasound only
  const row = (key: string, field: string, kind: Kind, extra: { compare?: boolean; only?: WireModality } = {}): DetailRow => ({
    key,
    label: label(key),
    kind,
    cells: obs.flatMap((o, j) => (extra.only && o.modalnosc !== extra.only ? [] : [{ tag: modality(o.modalnosc), path: ["zmiany", index, "obserwacje", j, field] }])),
    compare: extra.compare,
  });
  const rows = [
    row("type", "typ", "text"),
    row("places", "lokalizacje", "list"),
    row("clock", "godzina", "text"),
    row("fromNipple", "odleglosc_od_brodawki", "measure"),
    row("size", "wymiary", "size", { compare: true }),
    row("depth", "glebokosc", "measure", { only: "usg" }),
    row("shape", "ksztalt", WIRE_SHAPES, { compare: true }),
    row("margin", "brzeg", WIRE_MARGINS, { compare: true }),
    row("echo", "echogenicznosc", WIRE_ECHOES, { only: "usg" }),
    row("homogeneity", "jednorodnosc", WIRE_HOMOGENEITY, { only: "usg" }),
    row("skinInfiltration", "naciek_skory", "bool"),
  ];
  return rows.filter((r) => r.cells.length);
}

export function caseGroups(data: Extraction): DetailGroup[] {
  const single = (key: string, path: Path, kind: Kind): DetailRow => ({ key, label: label(key), kind, cells: [{ tag: null, path }] });
  const breasts = (key: string, field: Path, kind: Kind): DetailRow => ({
    key,
    label: label(key),
    kind,
    cells: (["lewa", "prawa"] as const).map((side) => ({ tag: t(`field.side.${SIDES[side]}` as MessageKey).toLowerCase(), path: ["piersi", side, ...field] })),
    allTag: t("detail.bothBreasts"),
  });
  return [
    { key: "study", title: null, rows: [single("modalities", ["modalnosci"], "fixed")] },
    {
      key: "breasts",
      title: label("breasts"),
      rows: [
        breasts("composition", ["budowa"], "text"),
        breasts("edema", ["obrzek"], "bool"),
        breasts("calcifications", ["zwapnienia"], "bool"),
        breasts("microcalcifications", ["mikrozwapnienia"], "bool"),
        breasts("focalLesions", ["zmiany_ogniskowe"], "bool"),
        breasts("skin", ["skora", "stan"], "text"),
        breasts("skinInfiltration", ["skora", "naciek"], "bool"),
      ],
    },
    ...data.wezly.map((node, i) => ({
      key: `node${i}`,
      title: [label("node"), node.okolica, t(`field.side.${SIDES[node.strona]}` as MessageKey).toLowerCase(), modality(node.modalnosc)].join(" · "),
      rows: [
        single("pathological", ["wezly", i, "patologiczne"], "bool"),
        single("count", ["wezly", i, "liczba"], WIRE_COUNTS),
        single("size", ["wezly", i, "wymiary"], "size"),
        single("notes", ["wezly", i, "uwagi"], "text"),
      ],
    })),
    {
      key: "conclusion",
      title: label("conclusion"),
      rows: [
        { ...single("birads", ["wniosek", "birads"], WIRE_BIRADS), check: conclusionBirads },
        single("text", ["wniosek", "tekst"], "text"),
        single("recommendation", ["wniosek", "zalecenie"], "text"),
      ],
    },
  ];
}

// the conclusion carries the highest category of its lesions
function conclusionBirads(report: Extraction): string | null {
  const rank = (b: string | null) => (b ? WIRE_BIRADS.indexOf(b as (typeof WIRE_BIRADS)[number]) : -1);
  const highest = report.zmiany.map((z) => z.birads).reduce<string | null>((a, b) => (rank(b) > rank(a) ? b : a), null);
  return highest && highest !== report.wniosek.birads ? t("detail.biradsNotHighest", { v: highest.toUpperCase() }) : null;
}

export const isEmpty = (value: unknown) => value === null || value === undefined || value === "" || (Array.isArray(value) && !value.length);

export function formatValue(kind: Kind, value: unknown): string {
  if (isEmpty(value)) return "—";
  if (kind === "bool") return t(value ? "detail.yes" : "detail.no");
  if (kind === "measure") return measureText(measureOfWire(value as WireMeasure)!);
  if (kind === "size") return sizeText(sizeOfWire(value as WireSize)!);
  if (kind === "fixed" || kind === "list") return (value as string[]).map((v) => (v === "usg" || v === "mammografia" ? modality(v) : v)).join(", ");
  if (kind === "text" && typeof value === "number") return formatNumber(value);
  return String(value);
}

// MG and USG disagree: other categories, or sizes 3 mm or more apart
export function disagree(kind: Kind, values: unknown[]): boolean {
  const present = values.filter((v) => !isEmpty(v));
  if (present.length < 2) return false;
  if (kind === "size") {
    const mm = present.map((v) => largestMm(sizeOfWire(v as WireSize)!) ?? 0);
    return Math.max(...mm) - Math.min(...mm) >= 3;
  }
  return new Set(present.map((v) => JSON.stringify(v))).size > 1;
}
