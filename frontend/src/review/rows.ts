import { formatNumber } from "../format";
import { t, type MessageKey } from "../i18n";
import {
  WIRE_BIRADS,
  WIRE_COUNTS,
  WIRE_ECHOES,
  WIRE_HOMOGENEITY,
  WIRE_MARGINS,
  WIRE_QUALIFIERS,
  WIRE_SHAPES,
  type Extraction,
  type WireMeasure,
  type WireModality,
  type WireQualifier,
  type WireSide,
  type WireSize,
  type WireUnit,
} from "./extraction";
import { areaOfClock, areaOfPlaces, areasDiffer, clockHours, FROM_WIRE, lesionType, TYPE_WIRE, toMm, type LesionType } from "./report";

// Every field of the report the doctor checks, by its path in the worker's JSON.

export type Path = (string | number)[];
export const pathKey = (path: Path) => path.join(".");
export const pathOf = (key: string): Path => key.split(".").map((step) => (/^\d+$/.test(step) ? Number(step) : step));

export type Kind =
  | { type: "choice"; options: readonly string[]; label?: (wire: string) => string }
  | { type: "text" }
  // a list of places, edited as one line
  | { type: "list" }
  | { type: "bool" }
  | { type: "measure"; unit: WireUnit }
  | { type: "size" }
  // ultrasound: clock and distance from the nipple, checked together
  | { type: "place" }
  // the category, written back as the report's own words when it stays the same
  | { type: "lesionType" }
  // a lymph node: region and side
  | { type: "where" };

export interface Note {
  text: string;
  // the part that differs
  emphasis: string;
}

export interface Row {
  key: string;
  label: string;
  kind: Kind;
  // one path, two for a pair (place, where) or for the two breasts
  paths: Path[];
  perSide?: boolean;
  // shown even when empty, as the report usually says it
  expected: (report: Extraction) => boolean;
  note?: (report: Extraction) => Note | null;
}

export interface Group {
  key: string;
  title: string;
  rows: Row[];
}

export type RowState = "todo" | "confirmed" | "corrected";
export type FieldCheck = "confirmed" | "corrected" | "unverified";

export function getAt(data: unknown, path: Path): unknown {
  return path.reduce<unknown>((node, step) => (node == null ? undefined : (node as Record<string | number, unknown>)[step]), data);
}

export const isEmpty = (value: unknown) => value === null || value === undefined || value === "" || (Array.isArray(value) && !value.length);
const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
const label = (key: string) => t(`row.${key}` as MessageKey);
const always = () => true;
const never = () => false;

const SIDE_CODE: Record<WireSide, "left" | "right" | "both"> = FROM_WIRE.side;
const sideLabel = (wire: string) => t(`field.side.${SIDE_CODE[wire as WireSide]}`).toLowerCase();
const modalityTitle = (m: WireModality) => t(m === "usg" ? "row.section.ultrasound" : "row.section.mammography");

// the lesion: side and its BI-RADS category
export function lesionGroup(i: number): Group {
  const at = (field: string): Path => ["zmiany", i, field];
  return {
    key: `lesion.${i}`,
    title: t("row.section.lesion", { n: i + 1 }),
    rows: [
      { key: pathKey(at("strona")), label: label("side"), kind: { type: "choice", options: ["lewa", "prawa", "obustronnie"], label: sideLabel }, paths: [at("strona")], expected: always },
      { key: pathKey(at("birads")), label: label("birads"), kind: { type: "choice", options: WIRE_BIRADS, label: (w) => w.toUpperCase() }, paths: [at("birads")], expected: always },
    ],
  };
}

// expected fields: what a report says about each kind of finding in each modality
function expects(category: LesionType | null, field: "place" | "shape" | "margin" | "echo") {
  const mass = category === "mass" || category === null;
  if (field === "place") return category !== "cyst" && category !== "other";
  return mass;
}

// one group for each observation (MG, USG) of the lesion
export function observationGroups(data: Extraction, i: number): Group[] {
  const obs = data.zmiany[i].obserwacje;
  return obs.map((o, j) => {
    const at = (field: string): Path => ["zmiany", i, "obserwacje", j, field];
    const usg = o.modalnosc === "usg";
    const twin = obs.filter((x) => x.modalnosc === o.modalnosc).length > 1;
    const category = (report: Extraction) => lesionType(getAt(report, at("typ")) as string | null);
    const when = (field: Parameters<typeof expects>[1]) => (report: Extraction) => expects(category(report), field);
    const row = (key: string, field: string, kind: Kind, expected: Row["expected"], extra: Partial<Row> = {}): Row => ({
      key: pathKey(at(field)),
      label: label(key),
      kind,
      paths: [at(field)],
      expected,
      ...extra,
    });
    const rows: Row[] = [
      row("type", "typ", { type: "lesionType" }, always),
      usg
        ? {
            key: pathKey(at("godzina")),
            label: label("place"),
            kind: { type: "place" },
            paths: [at("godzina"), at("odleglosc_od_brodawki")],
            expected: when("place"),
            note: (report) => placeNote(report, i, j),
          }
        : row("place", "lokalizacje", { type: "list" }, when("place")),
      row("size", "wymiary", { type: "size" }, always, { note: (report) => sizeNote(report, i, j) }),
      row("shape", "ksztalt", { type: "choice", options: WIRE_SHAPES }, when("shape")),
      row("margin", "brzeg", { type: "choice", options: WIRE_MARGINS }, when("margin")),
      ...(usg
        ? [
            row("echo", "echogenicznosc", { type: "choice", options: WIRE_ECHOES }, when("echo")),
            row("depth", "glebokosc", { type: "measure", unit: "mm" }, never),
            row("homogeneity", "jednorodnosc", { type: "choice", options: WIRE_HOMOGENEITY }, never),
            row("placeWords", "lokalizacje", { type: "list" }, never),
          ]
        : [row("clock", "godzina", { type: "text" }, never), row("fromNipple", "odleglosc_od_brodawki", { type: "measure", unit: "mm" }, never)]),
      row("skinInfiltration", "naciek_skory", { type: "bool" }, never),
    ];
    const number = twin ? ` ${obs.slice(0, j + 1).filter((x) => x.modalnosc === o.modalnosc).length}` : "";
    return { key: `obs.${i}.${j}`, title: modalityTitle(o.modalnosc) + number, rows };
  });
}

// breasts, lymph nodes and the conclusion: what the report says beyond its lesions
export function caseGroups(data: Extraction): Group[] {
  const breast = (key: string, field: Path, kind: Kind, expected: Row["expected"]): Row => ({
    key: pathKey(["piersi", ...field]),
    label: label(key),
    kind,
    paths: [
      ["piersi", "lewa", ...field],
      ["piersi", "prawa", ...field],
    ],
    perSide: true,
    expected,
  });
  const breasts: Group = {
    key: "breasts",
    title: t("row.section.breasts"),
    rows: [
      breast("composition", ["budowa"], { type: "text" }, always),
      breast("calcifications", ["zwapnienia"], { type: "bool" }, always),
      breast("microcalcifications", ["mikrozwapnienia"], { type: "bool" }, always),
      breast("focalLesions", ["zmiany_ogniskowe"], { type: "bool" }, always),
      breast("skin", ["skora", "stan"], { type: "text" }, always),
      breast("edema", ["obrzek"], { type: "bool" }, never),
      breast("skinInfiltration", ["skora", "naciek"], { type: "bool" }, never),
    ],
  };
  const nodes = data.wezly.map((node, k): Group => {
    const at = (field: string): Path => ["wezly", k, field];
    const pathological = (report: Extraction) => getAt(report, at("patologiczne")) === true;
    return {
      key: `node.${k}`,
      title: [t("row.section.node"), modalityTitle(node.modalnosc)].join(" · "),
      rows: [
        { key: pathKey(at("okolica")), label: label("nodeWhere"), kind: { type: "where" }, paths: [at("okolica"), at("strona")], expected: always },
        { key: pathKey(at("patologiczne")), label: label("pathological"), kind: { type: "bool" }, paths: [at("patologiczne")], expected: always },
        { key: pathKey(at("liczba")), label: label("count"), kind: { type: "choice", options: WIRE_COUNTS }, paths: [at("liczba")], expected: pathological },
        { key: pathKey(at("wymiary")), label: label("size"), kind: { type: "size" }, paths: [at("wymiary")], expected: pathological },
        { key: pathKey(at("uwagi")), label: label("notes"), kind: { type: "text" }, paths: [at("uwagi")], expected: never },
      ],
    };
  });
  const conclusion: Group = {
    key: "conclusion",
    title: t("row.section.conclusion"),
    rows: [
      {
        key: "wniosek.birads",
        label: label("birads"),
        kind: { type: "choice", options: WIRE_BIRADS, label: (w) => w.toUpperCase() },
        paths: [["wniosek", "birads"]],
        expected: always,
        note: conclusionNote,
      },
      { key: "wniosek.zalecenie", label: label("recommendation"), kind: { type: "text" }, paths: [["wniosek", "zalecenie"]], expected: always },
      { key: "wniosek.tekst", label: label("text"), kind: { type: "text" }, paths: [["wniosek", "tekst"]], expected: always },
    ],
  };
  return [breasts, ...nodes, conclusion];
}

// --- what is on screen and in which state ---

export interface Answers {
  // changed values by path
  edits: Record<string, unknown>;
  // paths confirmed as they are
  confirmed: string[];
  // fields taken out from under "+ inne pole", by row key
  added: string[];
}

export const NO_ANSWERS: Answers = { edits: {}, confirmed: [], added: [] };

export function applyAnswers(data: Extraction, edits: Answers["edits"]): Extraction {
  const copy: Extraction = structuredClone(data);
  for (const [key, value] of Object.entries(edits)) {
    const path = pathOf(key);
    const parent = getAt(copy, path.slice(0, -1)) as Record<string | number, unknown> | undefined;
    if (parent) parent[path[path.length - 1]] = value;
  }
  return copy;
}

// expected, filled in by the model or since, or added by the doctor
export function visibleRows(group: Group, original: Extraction, current: Extraction, added: string[]): Row[] {
  return group.rows.filter((r) => r.expected(current) || added.includes(r.key) || r.paths.some((p) => !isEmpty(getAt(original, p)) || !isEmpty(getAt(current, p))));
}

export const hiddenRows = (group: Group, original: Extraction, current: Extraction, added: string[]) => {
  const shown = visibleRows(group, original, current, added);
  return group.rows.filter((r) => !shown.includes(r));
};

export function rowState(row: Row, original: Extraction, current: Extraction, confirmed: string[]): RowState {
  if (row.paths.some((p) => !same(getAt(current, p), getAt(original, p)))) return "corrected";
  return row.paths.every((p) => confirmed.includes(pathKey(p))) ? "confirmed" : "todo";
}

export function waiting(group: Group, original: Extraction, current: Extraction, answers: Answers): Row[] {
  return visibleRows(group, original, current, answers.added).filter((r) => rowState(r, original, current, answers.confirmed) === "todo");
}

// a checked group vouches for its hidden fields too: the report doesn't say them
export function fieldChecks(groups: Group[], original: Extraction, current: Extraction, answers: Answers): Record<string, FieldCheck> {
  const checks: Record<string, FieldCheck> = {};
  for (const group of groups) {
    const done = !waiting(group, original, current, answers).length;
    const shown = visibleRows(group, original, current, answers.added);
    for (const row of group.rows) {
      const state = shown.includes(row) ? rowState(row, original, current, answers.confirmed) : done ? "confirmed" : "todo";
      for (const path of row.paths) {
        const changed = !same(getAt(current, path), getAt(original, path));
        checks[pathKey(path)] = changed ? "corrected" : state === "todo" ? "unverified" : "confirmed";
      }
    }
  }
  return checks;
}

// --- text on screen ---

const QUALIFIER_KEY: Record<WireQualifier, "exact" | "about" | "up_to"> = { dokładny: "exact", około: "about", do: "up_to" };

export function sizeText(size: WireSize): string {
  return t(`report.size.${QUALIFIER_KEY[size.kwalifikator]}`, { v: size.wartosci.map(formatNumber).join("×"), unit: size.jednostka });
}

const measureText = (m: WireMeasure) => `${formatNumber(m.wartosc)} ${m.jednostka}`;

// one value, or null for "nie podano"
export function valueText(kind: Kind, value: unknown): string | null {
  if (isEmpty(value)) return null;
  switch (kind.type) {
    case "choice":
      return kind.label ? kind.label(value as string) : (value as string);
    case "bool":
      return t(value ? "row.yes" : "row.no");
    case "list":
      return (value as string[]).join(", ");
    case "measure":
      return measureText(value as WireMeasure);
    case "size":
      return sizeText(value as WireSize);
    case "lesionType": {
      const category = lesionType(value as string);
      return category ? t(`field.type.${category}`) : null;
    }
    default:
      return String(value);
  }
}

export interface Line {
  text: string | null;
  // the area worked out from the clock, or "obie"
  extra?: string;
}

// a row as text: one line, or one for each breast when they differ
export function rowLines(row: Row, report: Extraction, side: WireSide | null = null): Line[] {
  const values = row.paths.map((p) => getAt(report, p));
  if (row.perSide) {
    const [left, right] = values.map((v) => valueText(row.kind, v));
    if (left === right) return [{ text: left, extra: t("row.bothSides") }];
    return [
      { text: right, extra: sideLabel("prawa") },
      { text: left, extra: sideLabel("lewa") },
    ];
  }
  if (row.kind.type === "place") {
    const [clock, distance] = values as [string | null, WireMeasure | null];
    if (!clock && !distance) return [{ text: null }];
    const parts = [clock ? t("report.clock", { h: clock.replace(/\s*(?:-|a)\s*/, "–") }) : t("row.noClock"), distance ? measureText(distance) : t("row.noDistance")];
    const area = side ? areaOfClock(clock, SIDE_CODE[side], distance ? { value: distance.wartosc, unit: distance.jednostka } : null) : null;
    return [{ text: parts.join(" · "), extra: area ? t(`field.quadrant.${area}`) : undefined }];
  }
  if (row.kind.type === "where") {
    const [region, nodeSide] = values as [string | null, WireSide | null];
    return [{ text: [region, nodeSide && sideLabel(nodeSide)].filter(Boolean).join(" · ") || null }];
  }
  return [{ text: valueText(row.kind, values[0]) }];
}

// --- comparisons, shown while the field waits ---

const largest = (s: WireSize | null) => (s?.wartosci.length ? toMm(Math.max(...s.wartosci), s.jednostka) : null);
const modalityShort = (m: WireModality) => t(m === "usg" ? "modality.ultrasound" : "modality.mammography");

function sizeNote(report: Extraction, i: number, j: number): Note | null {
  const obs = report.zmiany[i].obserwacje;
  const mine = largest(obs[j].wymiary);
  if (mine === null) return null;
  const other = obs.find((o, k) => k !== j && o.modalnosc !== obs[j].modalnosc && largest(o.wymiary) !== null);
  if (!other) return null;
  const gap = Math.abs(largest(other.wymiary)! - mine);
  if (gap < 3) return null;
  return { text: `${modalityShort(other.modalnosc)}: ${sizeText(other.wymiary!)}`, emphasis: t("row.sizeGap", { n: formatNumber(Math.round(gap)) }) };
}

function placeNote(report: Extraction, i: number, j: number): Note | null {
  const lesion = report.zmiany[i];
  const o = lesion.obserwacje[j];
  const fromNipple = o.odleglosc_od_brodawki ? { value: o.odleglosc_od_brodawki.wartosc, unit: o.odleglosc_od_brodawki.jednostka } : null;
  const mine = areaOfClock(o.godzina, SIDE_CODE[lesion.strona], fromNipple);
  const other = lesion.obserwacje.find((x) => x.modalnosc === "mammografia" && x.lokalizacje.length);
  if (!other || !areasDiffer(mine, areaOfPlaces(other.lokalizacje))) return null;
  return { text: `${modalityShort("mammografia")}: ${other.lokalizacje.join(", ")}`, emphasis: t("row.otherArea") };
}

// the conclusion carries the highest category of its lesions
function conclusionNote(report: Extraction): Note | null {
  const rank = (b: string | null) => (b ? WIRE_BIRADS.indexOf(b as (typeof WIRE_BIRADS)[number]) : -1);
  const highest = report.zmiany.map((z) => z.birads).reduce<string | null>((a, b) => (rank(b) > rank(a) ? b : a), null);
  if (!highest || !report.wniosek.birads || highest === report.wniosek.birads) return null;
  return { text: t("row.lesionsBirads", { v: highest.toUpperCase() }), emphasis: t("row.notConclusion") };
}

// --- reading the doctor's input back into the worker's shape ---

const number = (text: string) => {
  const value = Number(text.replace(",", ".").trim());
  return text.trim() && Number.isFinite(value) ? value : null;
};

export const validClock = (text: string) => !text.trim() || clockHours(text) !== null;
export const validNumber = (text: string) => !text.trim() || number(text) !== null;

export function readMeasure(text: string, unit: WireUnit): WireMeasure | null {
  const value = number(text);
  return value === null ? null : { wartosc: value, jednostka: unit };
}

export function readSize(values: string[], qualifier: WireQualifier, unit: WireUnit): WireSize | null {
  const numbers = values.map(number).filter((v): v is number => v !== null);
  return numbers.length ? { wartosci: numbers, jednostka: unit, kwalifikator: qualifier } : null;
}

export const readList = (text: string) =>
  text
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);

// a new category writes its plain name; the same one keeps the report's words
export function writeType(category: string, previous: string | null): string | null {
  if (!category) return null;
  return lesionType(previous) === category ? previous : TYPE_WIRE[category as LesionType];
}

export const QUALIFIERS = WIRE_QUALIFIERS;
export const qualifierLabel = (q: WireQualifier) => t(`row.qualifier.${QUALIFIER_KEY[q]}`);
