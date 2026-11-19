import type { Extraction, WireBiRads, WireEcho, WireLesion, WireMargin, WireModality, WireObservation, WireQualifier, WireShape, WireSide, WireSize, WireUnit } from "./extraction";

// The report as the app sees it: English codes, labels come from i18n.

export type Side = "left" | "right" | "both";
export type Modality = "mammography" | "ultrasound";
export type BiRads = "0" | "1" | "2" | "3" | "4" | "4A" | "4B" | "4C" | "5" | "6";
export type Shape = "oval" | "round" | "irregular";
export type Margin = "circumscribed" | "indistinct" | "obscured" | "microlobulated" | "angular" | "spiculated";
export type Echo = "anechoic" | "hypoechoic" | "isoechoic" | "hyperechoic" | "complex";
export type Quadrant = "upper_outer" | "upper_inner" | "lower_outer" | "lower_inner" | "central";
// a border hour or a range across one gives half of the breast
export type Area = Quadrant | "upper" | "lower" | "outer" | "inner";
export type LesionType = "mass" | "distortion" | "calcifications" | "cyst" | "other";
export type Unit = "mm" | "cm";
export type Qualifier = "exact" | "about" | "up_to";

export interface Measure {
  value: number;
  unit: Unit;
}

export interface Size {
  values: number[];
  unit: Unit;
  qualifier: Qualifier;
}

export interface Observation {
  modality: Modality;
  // straight from the report text
  places: string[];
  clock: string | null;
  fromNipple: Measure | null;
  type: string | null;
  size: Size | null;
  depth: Measure | null;
  shape: Shape | null;
  margin: Margin | null;
  echo: Echo | null;
  quote: string;
}

export interface Lesion {
  id: number;
  side: Side;
  birads: BiRads | null;
  observations: Observation[];
}

export interface Conclusion {
  birads: BiRads | null;
  text: string | null;
  recommendation: string | null;
}

export interface Report {
  lesions: Lesion[];
  conclusion: Conclusion;
}

const SIDES: Record<WireSide, Side> = { lewa: "left", prawa: "right", obustronnie: "both" };
const MODALITIES: Record<WireModality, Modality> = { mammografia: "mammography", usg: "ultrasound" };
const SHAPES: Record<WireShape, Shape> = { owalny: "oval", okrągły: "round", nieregularny: "irregular" };
const MARGINS: Record<WireMargin, Margin> = {
  obwiedziony: "circumscribed",
  nieostry: "indistinct",
  zatarty: "obscured",
  mikropłatowaty: "microlobulated",
  kątowy: "angular",
  spikularny: "spiculated",
};
const ECHOES: Record<WireEcho, Echo> = {
  bezechowa: "anechoic",
  hipoechogeniczna: "hypoechoic",
  izoechogeniczna: "isoechoic",
  hiperechogeniczna: "hyperechoic",
  złożona: "complex",
};
const QUALIFIERS: Record<WireQualifier, Qualifier> = { dokładny: "exact", około: "about", do: "up_to" };

const invert = <W extends string, A extends string>(map: Record<W, A>) =>
  Object.fromEntries(Object.entries(map).map(([wire, code]) => [code, wire])) as Record<A, W>;

export const FROM_WIRE = { side: SIDES, shape: SHAPES, margin: MARGINS };

// for saving the doctor's answers in the worker's schema
export const TO_WIRE = {
  side: invert(SIDES),
  shape: invert(SHAPES),
  margin: invert(MARGINS),
  echo: invert(ECHOES),
  birads: (value: BiRads) => value.toLowerCase() as WireBiRads,
};

// Polish on purpose: these match the report's own text
const REPORT_WORDS = {
  central: /zabrodawk|centraln/,
  upper: /górn|gorn/,
  lower: /doln/,
  outer: /zewn/,
  inner: /wewn/,
  birads: /bi-?rads/i,
};

// the worker keeps the type as written; most specific first, so "ognisko zaburzonej architektoniki" is a distortion
const TYPE_WORDS: [LesionType, RegExp][] = [
  ["distortion", /architekt/i],
  ["calcifications", /zwapnie/i],
  ["cyst", /torbiel/i],
  ["mass", /ognisk|guz|zmian/i],
];
export const TYPE_WIRE: Record<LesionType, string> = {
  mass: "zmiana ogniskowa",
  distortion: "zaburzenie architektoniki",
  calcifications: "skupisko mikrozwapnień",
  cyst: "torbiel",
  other: "inna",
};

export function lesionType(type: string | null): LesionType | null {
  if (!type) return null;
  return TYPE_WORDS.find(([, words]) => words.test(type))?.[0] ?? "other";
}

const toBiRads = (value: WireBiRads | null) => (value ? (value.toUpperCase() as BiRads) : null);
export const sizeOfWire = (s: WireSize | null): Size | null => (s ? { values: s.wartosci, unit: s.jednostka, qualifier: QUALIFIERS[s.kwalifikator] } : null);
export const measureOfWire = (m: { wartosc: number; jednostka: WireUnit } | null): Measure | null => (m ? { value: m.wartosc, unit: m.jednostka } : null);

function observation(o: WireObservation): Observation {
  return {
    modality: MODALITIES[o.modalnosc],
    places: o.lokalizacje,
    clock: o.godzina,
    fromNipple: measureOfWire(o.odleglosc_od_brodawki),
    type: o.typ,
    size: sizeOfWire(o.wymiary),
    depth: measureOfWire(o.glebokosc),
    shape: o.ksztalt ? SHAPES[o.ksztalt] : null,
    margin: o.brzeg ? MARGINS[o.brzeg] : null,
    echo: o.echogenicznosc ? ECHOES[o.echogenicznosc] : null,
    quote: o.cytat,
  };
}

const lesion = (z: WireLesion): Lesion => ({ id: z.id, side: SIDES[z.strona], birads: toBiRads(z.birads), observations: z.obserwacje.map(observation) });

export function fromExtraction(data: Extraction): Report {
  return {
    lesions: data.zmiany.map(lesion),
    conclusion: { birads: toBiRads(data.wniosek.birads), text: data.wniosek.tekst, recommendation: data.wniosek.zalecenie },
  };
}

export const toMm = (value: number, unit: Unit) => (unit === "cm" ? value * 10 : value);
export const largestMm = (s: Size) => (s.values.length ? toMm(Math.max(...s.values), s.unit) : null);

// "8", "10/11", "2-3", "2 a 3"
const CLOCK = /^\s*(\d{1,2})(?:\s*(?:-|–|\/|a)\s*(\d{1,2}))?\s*$/;

export function clockHours(clock: string | null): number[] | null {
  const match = CLOCK.exec(clock ?? "");
  if (!match) return null;
  const [from, to] = [Number(match[1]), match[2] ? Number(match[2]) : null];
  if (from < 1 || from > 12 || (to !== null && (to < 1 || to > 12))) return null;
  if (to === null || to === from) return [from];
  // the shorter way round the clock
  const step = (to - from + 12) % 12 <= 6 ? 1 : -1;
  const hours = [from];
  for (let h = from; h !== to; ) hours.push((h = ((h + step + 11) % 12) + 1));
  return hours;
}

// right breast: 9 o'clock is outer, left: 3; 12, 3, 6 and 9 sit on a border
function quadrantsAt(at: number, side: "left" | "right"): string[] {
  const vertical = at === 3 || at === 9 ? ["upper", "lower"] : at > 9 || at < 3 ? ["upper"] : ["lower"];
  const outer = side === "right" ? at > 6 && at < 12 : at > 0 && at < 6;
  const horizontal = at === 12 || at === 6 ? ["outer", "inner"] : [outer ? "outer" : "inner"];
  return vertical.flatMap((v) => horizontal.map((h) => `${v}_${h}`));
}

// a range lies between its hours, so "2-3" stays above the 3 o'clock border
function clockPoints(hours: number[]): number[] {
  if (hours.length === 1) return hours;
  const step = hours[1] === (hours[0] % 12) + 1 ? 0.5 : -0.5;
  return hours.slice(0, -1).map((h) => ((h + step + 11.5) % 12) + 0.5);
}

// one quadrant, two next to each other make a half, more say nothing
function areaOf(quadrants: Set<string>): Area | null {
  const all = [...quadrants];
  if (all.length === 1) return all[0] as Area;
  if (all.length !== 2) return null;
  const [[v1, h1], [v2, h2]] = all.map((q) => q.split("_"));
  if (v1 === v2) return v1 as Area;
  if (h1 === h2) return h1 as Area;
  return null;
}

export function areaOfClock(clock: string | null, side: Side, fromNipple: Measure | null): Area | null {
  if (fromNipple?.value === 0) return "central";
  const hours = clockHours(clock);
  if (!hours || side === "both") return null;
  return areaOf(new Set(clockPoints(hours).flatMap((at) => quadrantsAt(at, side))));
}

export function areaOfPlaces(places: string[]): Area | null {
  const text = places.join(" ").toLowerCase();
  if (REPORT_WORDS.central.test(text)) return "central";
  const upper = REPORT_WORDS.upper.test(text);
  const lower = REPORT_WORDS.lower.test(text);
  const outer = REPORT_WORDS.outer.test(text);
  const inner = REPORT_WORDS.inner.test(text);
  const vertical = upper === lower ? null : upper ? "upper" : "lower";
  const horizontal = outer === inner ? null : outer ? "outer" : "inner";
  if (vertical && horizontal) return `${vertical}_${horizontal}`;
  return vertical ?? horizontal;
}

const quadrantsOf = (area: Area): string[] =>
  area.includes("_") ? [area] : ["upper_outer", "upper_inner", "lower_outer", "lower_inner"].filter((q) => q.split("_").includes(area));

// central, or one of them unknown, can't disagree
export function areasDiffer(a: Area | null, b: Area | null): boolean {
  if (!a || !b || a === "central" || b === "central") return false;
  const other = quadrantsOf(b);
  return !quadrantsOf(a).some((q) => other.includes(q));
}

export const quotesBirads = (l: Lesion) => l.observations.some((o) => REPORT_WORDS.birads.test(o.quote));
