import { formatNumber } from "../format";
import { t, type MessageKey } from "../i18n";
import type { Extraction } from "./extraction";
import {
  largestMm,
  QUADRANT_WIRE,
  quadrantOfClock,
  quadrantOfPlaces,
  quotesBirads,
  TO_WIRE,
  type BiRads,
  type Conclusion,
  type Echo,
  type Lesion,
  type Margin,
  type Measure,
  type Observation,
  type Quadrant,
  type Shape,
  type Side,
  type Size,
} from "./report";

// values are codes, labels come from i18n
export interface FieldDef {
  key: "side" | "birads" | "location" | "size" | "shape" | "margin" | "echo";
  options?: readonly string[];
  unit?: string;
}

export const FIELDS: FieldDef[] = [
  { key: "side", options: ["left", "right", "both"] satisfies Side[] },
  { key: "birads", options: ["0", "1", "2", "3", "4", "4A", "4B", "4C", "5", "6"] satisfies BiRads[] },
  { key: "location", options: ["upper_outer", "upper_inner", "lower_outer", "lower_inner", "central"] satisfies Quadrant[] },
  { key: "size", unit: "mm" },
  { key: "shape", options: ["oval", "round", "irregular"] satisfies Shape[] },
  { key: "margin", options: ["circumscribed", "indistinct", "obscured", "microlobulated", "angular", "spiculated"] satisfies Margin[] },
  { key: "echo", options: ["anechoic", "hypoechoic", "isoechoic", "hyperechoic", "complex"] satisfies Echo[] },
];

export type FieldKey = FieldDef["key"];

export const fieldLabel = (key: FieldKey) => t(`field.${key}`);

// BI-RADS categories read the same in every language
export const optionLabel = (key: FieldKey, value: string) => (!value || key === "birads" || key === "size" ? value : t(`field.${key}.${value}` as MessageKey));

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

const modality = (o: Observation) => t(`modality.${o.modality}`);
const measureText = (m: Measure) => `${formatNumber(m.value)} ${m.unit}`;
const sizeText = (s: Size) => t(`report.size.${s.qualifier}`, { v: s.values.map(formatNumber).join("×"), unit: s.unit });

function placeText(o: Observation) {
  const parts = [o.clock && t("report.clock", { h: o.clock }), o.fromNipple && t("report.fromNipple", { v: measureText(o.fromNipple) })];
  return [...parts.filter(Boolean), ...o.places].join(", ");
}

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

const quadrantOf = (o: Observation, side: Side) => quadrantOfClock(o.clock, side) ?? quadrantOfPlaces(o.places);
const missing = () => [t("review.hint.missing")];

export function lesionFields(lesion: Lesion, conclusion: Conclusion): Proposals {
  const obs = lesion.observations;
  const sized = sizeSource(lesion);
  // the sized observation goes first
  const order = sized === null ? obs.map((_, i) => i) : [sized, ...obs.map((_, i) => i).filter((i) => i !== sized)];
  const pick = (has: (o: Observation) => unknown) => order.find((i) => has(obs[i]));
  const fields: Proposals = { side: { value: lesion.side } };

  const birads = lesion.birads ?? conclusion.birads;
  fields.birads = {
    value: birads ?? "",
    hints: birads ? undefined : missing(),
    check: !birads || quotesBirads(lesion) ? undefined : t(birads === conclusion.birads ? "review.hint.biradsFromConclusion" : "review.hint.biradsNotInLesion"),
  };

  const located = pick((o) => quadrantOf(o, lesion.side));
  const places = obs.filter((o) => placeText(o)).map((o) => `${placeText(o)} · ${modality(o)}`);
  fields.location = {
    value: located === undefined ? "" : quadrantOf(obs[located], lesion.side)!,
    from: located ?? pick((o) => placeText(o)),
    hints: places.length ? places : missing(),
  };

  if (sized === null) {
    fields.size = { value: "", hints: missing() };
  } else {
    const o = obs[sized];
    const depth = o.depth ? `, ${t("report.depth", { v: measureText(o.depth) })}` : "";
    const others = obs.filter((x, i) => i !== sized && x.size).map((x) => `${modality(x)}: ${sizeText(x.size!)}`);
    fields.size = {
      value: String(Math.round(largestMm(o.size!)! * 10) / 10),
      from: sized,
      hints: [`${sizeText(o.size!)}${depth} · ${modality(o)}`, ...others],
    };
  }

  const shapeAt = pick((o) => o.shape);
  fields.shape = shapeAt === undefined ? { value: "", hints: missing() } : { value: obs[shapeAt].shape!, from: shapeAt };

  const marginAt = pick((o) => o.margin);
  fields.margin = marginAt === undefined ? { value: "", hints: missing() } : { value: obs[marginAt].margin!, from: marginAt };

  // ultrasound only
  const ultrasound = obs.findIndex((o) => o.modality === "ultrasound");
  if (ultrasound >= 0) {
    const echoAt = pick((o) => o.echo);
    fields.echo = {
      value: echoAt === undefined ? "" : obs[echoAt].echo!,
      from: echoAt ?? ultrasound,
      hints: echoAt === undefined ? missing() : [t("review.hint.ultrasoundOnly")],
    };
  }
  return fields;
}

export function lesionSummary(lesion: Lesion): string {
  const sized = sizeSource(lesion);
  const o = lesion.observations[sized ?? 0];
  const where = o?.clock ? t("report.clock", { h: o.clock }) : o?.type;
  return [t(`review.lesion.side.${lesion.side}`), where, sized !== null && sizeText(lesion.observations[sized].size!)].filter(Boolean).join(" · ");
}

// so the approved report has the model's shape
export function applyAnswers(data: Extraction, lesions: Record<number, { proposals: Proposals; values: Partial<Record<FieldKey, string>> }>): Extraction {
  const copy: Extraction = structuredClone(data);
  for (const wire of copy.zmiany) {
    const answer = lesions[wire.id];
    if (!answer) continue;
    const { proposals, values } = answer;
    const changed = (key: FieldKey) => values[key] !== undefined && values[key] !== proposals[key]?.value;
    const at = (key: FieldKey) => wire.obserwacje[proposals[key]?.from ?? 0];

    if (changed("side")) wire.strona = TO_WIRE.side[values.side as Side];
    if (changed("birads")) wire.birads = values.birads ? TO_WIRE.birads(values.birads as BiRads) : null;
    if (changed("location") && at("location")) at("location").lokalizacje = values.location ? [QUADRANT_WIRE[values.location as Quadrant]] : [];
    if (changed("size") && at("size")) {
      const mm = Number(values.size);
      at("size").wymiary = values.size && Number.isFinite(mm) ? { wartosci: [mm], jednostka: "mm", kwalifikator: "dokładny" } : null;
    }
    if (changed("shape") && at("shape")) at("shape").ksztalt = values.shape ? TO_WIRE.shape[values.shape as Shape] : null;
    if (changed("margin") && at("margin")) at("margin").brzeg = values.margin ? TO_WIRE.margin[values.margin as Margin] : null;
    if (changed("echo") && at("echo")) at("echo").echogenicznosc = values.echo ? TO_WIRE.echo[values.echo as Echo] : null;
  }
  return copy;
}
