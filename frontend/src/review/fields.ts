import { formatNumber } from "../format";
import { hasMessage, t, type MessageKey } from "../i18n";
import type { Extraction } from "./extraction";
import {
  largestMm,
  lesionType,
  quadrantOfClock,
  quadrantOfPlaces,
  quotesBirads,
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
  fields.shape = shapeAt === undefined ? { value: "", hints: missing() } : { value: obs[shapeAt].shape!, from: shapeAt };

  const marginAt = pick((o) => o.margin);
  fields.margin = marginAt === undefined ? { value: "", hints: missing() } : { value: obs[marginAt].margin!, from: marginAt };
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

// so the approved report has the model's shape
export function applyAnswers(data: Extraction, lesions: Record<number, { proposals: Proposals; values: Values }>): Extraction {
  const copy: Extraction = structuredClone(data);
  for (const wire of copy.zmiany) {
    const answer = lesions[wire.id];
    if (!answer) continue;
    const { proposals, values } = answer;
    const changed = (key: FieldKey) => values[key] !== undefined && values[key] !== proposals[key]?.value;
    const at = (key: FieldKey) => wire.obserwacje[proposals[key]?.from ?? 0];
    const number = (key: FieldKey) => (values[key] && Number.isFinite(Number(values[key])) ? Number(values[key]) : null);

    if (changed("side")) wire.strona = TO_WIRE.side[values.side as Side];
    if (changed("type") && at("type")) at("type").typ = values.type ? TYPE_WIRE[values.type as LesionType] : null;
    if (changed("clock") && at("clock")) at("clock").godzina = values.clock || null;
    if (changed("distance") && at("distance")) {
      const cm = number("distance");
      at("distance").odleglosc_od_brodawki = cm === null ? null : { wartosc: cm, jednostka: "cm" };
    }
    if (changed("size") && at("size")) {
      const mm = number("size");
      at("size").wymiary = mm === null ? null : { wartosci: [mm], jednostka: "mm", kwalifikator: "dokładny" };
    }
    if (changed("birads")) wire.birads = values.birads ? TO_WIRE.birads(values.birads as BiRads) : null;
    if (changed("shape") && at("shape")) at("shape").ksztalt = values.shape ? TO_WIRE.shape[values.shape as Shape] : null;
    if (changed("margin") && at("margin")) at("margin").brzeg = values.margin ? TO_WIRE.margin[values.margin as Margin] : null;
  }
  return copy;
}
