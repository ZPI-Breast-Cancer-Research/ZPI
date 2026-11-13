import type { Extraction, WireBiRads, WireEcho, WireLesion, WireMargin, WireModality, WireObservation, WireQualifier, WireShape, WireSide, WireSize, WireUnit } from "./extraction";

// The report as the app sees it: English codes, labels come from i18n.

export type Side = "left" | "right" | "both";
export type Modality = "mammography" | "ultrasound";
export type BiRads = "0" | "1" | "2" | "3" | "4" | "4A" | "4B" | "4C" | "5" | "6";
export type Shape = "oval" | "round" | "irregular";
export type Margin = "circumscribed" | "indistinct" | "obscured" | "microlobulated" | "angular" | "spiculated";
export type Echo = "anechoic" | "hypoechoic" | "isoechoic" | "hyperechoic" | "complex";
export type Quadrant = "upper_outer" | "upper_inner" | "lower_outer" | "lower_inner" | "central";
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

// right breast: 9 o'clock is outer, left: 3; 12, 3, 6 and 9 sit on a border
export function quadrantOfClock(clock: string | null, side: Side): Quadrant | null {
  const hour = Number.parseInt(clock ?? "", 10);
  if (!hour || hour > 12 || side === "both" || hour % 3 === 0) return null;
  const upper = hour >= 10 || hour <= 2;
  const outer = side === "right" ? hour >= 7 : hour <= 5;
  return `${upper ? "upper" : "lower"}_${outer ? "outer" : "inner"}`;
}

export function quadrantOfPlaces(places: string[]): Quadrant | null {
  const text = places.join(" ").toLowerCase();
  if (REPORT_WORDS.central.test(text)) return "central";
  const upper = REPORT_WORDS.upper.test(text);
  const lower = REPORT_WORDS.lower.test(text);
  const outer = REPORT_WORDS.outer.test(text);
  const inner = REPORT_WORDS.inner.test(text);
  if (upper === lower || outer === inner) return null;
  return `${upper ? "upper" : "lower"}_${outer ? "outer" : "inner"}`;
}

export const quotesBirads = (l: Lesion) => l.observations.some((o) => REPORT_WORDS.birads.test(o.quote));
