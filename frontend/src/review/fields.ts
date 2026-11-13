import { formatNumber } from "../format";
import { hasMessage, t, type MessageKey } from "../i18n";
import type { WireMargin, WireMeasure, WireShape, WireSide, WireSize } from "./extraction";
import {
  FROM_WIRE,
  largestMm,
  lesionType,
  quadrantOfClock,
  quadrantOfPlaces,
  quotesBirads,
  sizeOfWire,
  TO_WIRE,
  toMm,
  TYPE_WIRE,
  type BiRads,
  type Conclusion,
  type Lesion,
  type LesionType,
  type Margin,
  type Measure,
  type Observation,
  type Shape,
  type Side,
  type Size,
} from "./report";

// values are codes, labels come from i18n
export interface FieldDef {
  key: "side" | "type" | "clock" | "distance" | "size" | "birads" | "shape" | "margin";
  options?: readonly string[];
  unit?: string;
  // shown in the row of another field and confirmed with it
  row?: FieldDef["key"];
  narrow?: boolean;
}

const HOURS = Array.from({ length: 12 }, (_, i) => String(i + 1));

export const FIELDS: FieldDef[] = [
  { key: "side", options: ["left", "right", "both"] satisfies Side[] },
  { key: "type", options: ["mass", "distortion", "calcifications", "cyst", "other"] satisfies LesionType[] },
  { key: "clock", options: HOURS, narrow: true },
  { key: "distance", unit: "cm", row: "clock", narrow: true },
  { key: "size", unit: "mm", narrow: true },
  { key: "birads", options: ["0", "1", "2", "3", "4", "4A", "4B", "4C", "5", "6"] satisfies BiRads[], narrow: true },
  { key: "shape", options: ["oval", "round", "irregular"] satisfies Shape[] },
  { key: "margin", options: ["circumscribed", "indistinct", "obscured", "microlobulated", "angular", "spiculated"] satisfies Margin[] },
];

export type FieldKey = FieldDef["key"];
export type Values = Partial<Record<FieldKey, string>>;

export const fieldLabel = (key: FieldKey) => t(`field.${key}`);

// any extraction field; an older backend sends a label instead
export const anyFieldLabel = (field: string) => (hasMessage(`field.${field}`) ? t(`field.${field}` as MessageKey) : field);

// BI-RADS categories and numbers read the same in every language
export function optionLabel(key: FieldKey, value: string) {
  if (!value || key === "birads" || key === "size" || key === "distance") return value;
  if (key === "clock") return t("report.clock", { h: value });
  return t(`field.${key}.${value}` as MessageKey);
}

// shape and margin describe a mass, not calcifications, a distortion or a cyst
const MASS_ONLY: FieldKey[] = ["shape", "margin"];
const describesMass = (type: string) => !type || type === "mass" || type === "other";

export interface Proposal {
  value: string;
  // where the value came from, shown under the field
  hints?: string[];
  // why to look twice ("Sprawdź")
  check?: string;
  // so a correction lands in the same observation
  from?: number;
}

export type Proposals = Partial<Record<FieldKey, Proposal>>;

// the fields this lesion asks for, with the type as picked now
export function keysFor(proposals: Proposals, values: Values): FieldKey[] {
  const type = values.type ?? proposals.type?.value ?? "";
  return FIELDS.filter((f) => proposals[f.key] && (describesMass(type) || !MASS_ONLY.includes(f.key))).map((f) => f.key);
}

const modality = (o: Observation) => t(`modality.${o.modality}`);
export const measureText = (m: Measure) => `${formatNumber(m.value)} ${m.unit}`;
export const sizeText = (s: Size) => t(`report.size.${s.qualifier}`, { v: s.values.map(formatNumber).join("×"), unit: s.unit });
const round = (n: number) => String(Math.round(n * 10) / 10);

// exact before "about", then the larger one
function sizeSource(lesion: Lesion): number | null {
  let best: number | null = null;
  lesion.observations.forEach((o, i) => {
    if (!o.size || largestMm(o.size) === null) return;
    if (best === null) return (best = i);
    const current = lesion.observations[best].size!;
    const exact = o.size.qualifier === "exact";
    if (exact !== (current.qualifier === "exact") ? exact : largestMm(o.size)! > largestMm(current)!) best = i;
  });
  return best;
}

const missing = () => [t("review.hint.missing")];

export function lesionFields(lesion: Lesion, conclusion: Conclusion, lesionCount: number): Proposals {
  const obs = lesion.observations;
  const sized = sizeSource(lesion);
  // the sized observation goes first
  const order = sized === null ? obs.map((_, i) => i) : [sized, ...obs.map((_, i) => i).filter((i) => i !== sized)];
  const pick = (has: (o: Observation) => unknown) => order.find((i) => has(obs[i]));
  const fields: Proposals = { side: { value: lesion.side } };

  const typed = pick((o) => o.type);
  fields.type = typed === undefined ? { value: "", hints: missing() } : { value: lesionType(obs[typed].type)!, from: typed, hints: [`${obs[typed].type} · ${modality(obs[typed])}`] };

  const clocked = pick((o) => o.clock);
  const quadrant = (clocked !== undefined && quadrantOfClock(obs[clocked].clock, lesion.side)) || quadrantOfPlaces(obs.flatMap((o) => o.places));
  const places = obs.filter((o) => o.places.length).map((o) => `${o.places.join(", ")} · ${modality(o)}`);
  const where = [...(quadrant ? [t(`field.quadrant.${quadrant}`)] : []), ...places];
  fields.clock = { value: clocked === undefined ? "" : String(Number.parseInt(obs[clocked].clock!, 10) || ""), from: clocked ?? pick((o) => o.places.length), hints: where.length ? where : missing() };

  const nippled = pick((o) => o.fromNipple);
  fields.distance =
    nippled === undefined ? { value: "", from: clocked } : { value: round(toMm(obs[nippled].fromNipple!.value, obs[nippled].fromNipple!.unit) / 10), from: nippled };

  if (sized === null) {
    fields.size = { value: "", hints: missing() };
  } else {
    const o = obs[sized];
    const depth = o.depth ? `, ${t("report.depth", { v: measureText(o.depth) })}` : "";
    const others = obs.filter((x, i) => i !== sized && x.size).map((x) => `${modality(x)}: ${sizeText(x.size!)}`);
    fields.size = { value: round(largestMm(o.size!)!), from: sized, hints: [`${sizeText(o.size!)}${depth} · ${modality(o)}`, ...others] };
  }

  // with several lesions the conclusion's category may belong to another one
  const birads = lesion.birads ?? (lesionCount === 1 ? conclusion.birads : null);
  fields.birads = {
    value: birads ?? "",
    hints: birads ? undefined : missing(),
    check: !birads || quotesBirads(lesion) ? undefined : t(birads === conclusion.birads ? "review.hint.biradsFromConclusion" : "review.hint.biradsNotInLesion"),
  };

  const shapeAt = pick((o) => o.shape);
  fields.shape = shapeAt === undefined ? { value: "", hints: missing() } : { value: obs[shapeAt].shape!, from: shapeAt, hints: [modality(obs[shapeAt])] };

  const marginAt = pick((o) => o.margin);
  fields.margin = marginAt === undefined ? { value: "", hints: missing() } : { value: obs[marginAt].margin!, from: marginAt, hints: [modality(obs[marginAt])] };
  return fields;
}

export function lesionSummary(lesion: Lesion): string {
  const sized = sizeSource(lesion);
  const o = lesion.observations[sized ?? 0];
  const where = o?.clock ? t("report.clock", { h: o.clock }) : o?.type;
  return [t(`review.lesion.side.${lesion.side}`), where, sized !== null && sizeText(lesion.observations[sized].size!)].filter(Boolean).join(" · ");
}

const WIRE_FIELD: Partial<Record<FieldKey, string>> = { type: "typ", clock: "godzina", distance: "odleglosc_od_brodawki", size: "wymiary", shape: "ksztalt", margin: "brzeg" };

// where an answer of the short form lives in the worker's JSON
export function wirePath(lesionIndex: number, key: FieldKey, proposal?: Proposal): (string | number)[] {
  if (key === "side") return ["zmiany", lesionIndex, "strona"];
  if (key === "birads") return ["zmiany", lesionIndex, "birads"];
  return ["zmiany", lesionIndex, "obserwacje", proposal?.from ?? 0, WIRE_FIELD[key]!];
}

const parse = (value: string) => (value.trim() && Number.isFinite(Number(value)) ? Number(value) : null);

// a value in the worker's JSON as the short form shows it
export function formValue(key: FieldKey, wire: unknown): string {
  if (wire === null || wire === undefined || wire === "") return "";
  if (key === "side") return FROM_WIRE.side[wire as WireSide];
  if (key === "birads") return (wire as string).toUpperCase();
  if (key === "type") return lesionType(wire as string) ?? "";
  if (key === "clock") return String(Number.parseInt(wire as string, 10) || "");
  if (key === "distance") return round(toMm((wire as WireMeasure).wartosc, (wire as WireMeasure).jednostka) / 10);
  if (key === "size") return round(largestMm(sizeOfWire(wire as WireSize)!) ?? 0);
  if (key === "shape") return FROM_WIRE.shape[wire as WireShape];
  return FROM_WIRE.margin[wire as WireMargin];
}

// back in the worker's shape; a size keeps its other dimensions and qualifier
export function wireValue(key: FieldKey, value: string, previous: unknown): unknown {
  if (!value) return null;
  if (key === "side") return TO_WIRE.side[value as Side];
  if (key === "birads") return TO_WIRE.birads(value as BiRads);
  if (key === "type") return lesionType(previous as string | null) === value ? previous : TYPE_WIRE[value as LesionType];
  if (key === "clock") return value;
  if (key === "shape") return TO_WIRE.shape[value as Shape];
  if (key === "margin") return TO_WIRE.margin[value as Margin];
  const number = parse(value);
  if (number === null) return previous ?? null;
  if (key === "distance") {
    const unit = (previous as WireMeasure | null)?.jednostka ?? "cm";
    return { wartosc: unit === "mm" ? number * 10 : number, jednostka: unit };
  }
  const size = previous as WireSize | null;
  if (!size?.wartosci.length) return { wartosci: [number], jednostka: "mm", kwalifikator: "dokładny" };
  const largest = size.wartosci.indexOf(Math.max(...size.wartosci));
  const wartosci = size.wartosci.map((v, i) => (i === largest ? (size.jednostka === "cm" ? number / 10 : number) : v));
  return { ...size, wartosci };
}
