// 1:1 with workers/extraction/schema.py (v3). The Polish names are the worker's, so they stay here;
// report.ts translates them for the rest of the app.

export type WireModality = "mammografia" | "usg";
export type WireSide = "lewa" | "prawa" | "obustronnie";
export type WireBiRads = "0" | "1" | "2" | "3" | "4" | "4a" | "4b" | "4c" | "5" | "6";
export type WireUnit = "mm" | "cm";
export type WireQualifier = "dokładny" | "około" | "do";
export type WireShape = "okrągły" | "owalny" | "nieregularny";
export type WireMargin = "obwiedziony" | "nieostry" | "zatarty" | "mikropłatowaty" | "kątowy" | "spikularny";
export type WireEcho = "bezechowa" | "hipoechogeniczna" | "izoechogeniczna" | "hiperechogeniczna" | "złożona";
export type WireHomogeneity = "jednorodna" | "niejednorodna";

export interface WireMeasure {
  wartosc: number;
  jednostka: WireUnit;
}

export interface WireSize {
  wartosci: number[];
  jednostka: WireUnit;
  kwalifikator: WireQualifier;
}

export interface WireBreast {
  budowa: string | null;
  obrzek: boolean | null;
  zwapnienia: boolean | null;
  mikrozwapnienia: boolean | null;
  zmiany_ogniskowe: boolean | null;
  skora: { stan: string | null; naciek: boolean | null };
}

export interface WireObservation {
  modalnosc: WireModality;
  lokalizacje: string[];
  godzina: string | null;
  odleglosc_od_brodawki: WireMeasure | null;
  typ: string | null;
  wymiary: WireSize | null;
  glebokosc: WireMeasure | null;
  ksztalt: WireShape | null;
  brzeg: WireMargin | null;
  echogenicznosc: WireEcho | null;
  jednorodnosc: WireHomogeneity | null;
  naciek_skory: boolean | null;
  cytat: string;
}

export interface WireLesion {
  id: number;
  strona: WireSide;
  // only if the report names it at the lesion
  birads: WireBiRads | null;
  obserwacje: WireObservation[];
  polaczenie_obserwacji: { pewne: boolean; powod: string | null } | null;
}

export interface WireNode {
  modalnosc: WireModality;
  strona: WireSide;
  okolica: string;
  liczba: "pojedynczy" | "mnogie" | null;
  wymiary: WireSize | null;
  patologiczne: boolean | null;
  uwagi: string | null;
  cytat: string;
}

export interface WireConclusion {
  birads: WireBiRads | null;
  tekst: string | null;
  zalecenie: string | null;
}

export interface Extraction {
  modalnosci: WireModality[];
  piersi: { lewa: WireBreast; prawa: WireBreast };
  zmiany: WireLesion[];
  wezly: WireNode[];
  wniosek: WireConclusion;
}

export interface Provenance {
  ocr_engine: string | null;
  ocr_engine_version: string | null;
  ocr_mean_confidence: number | null;
  orientation_detector: string | null;
  // counter-clockwise, as PIL turns it
  page_rotations: (number | null)[];
  llm_provider: string;
  llm_model: string;
  prompt_version: string;
  schema_version: string;
}

export interface ExtractionResult {
  source: string;
  status: "ok" | "error";
  data: Extraction | null;
  error: string | null;
  warnings: string[];
  // OCR text, the quotes come from here
  text: string;
  provenance: Provenance;
  attempts: number;
  ocr_seconds: number | null;
  llm_seconds: number | null;
  created_at: string;
}

export interface CaseReport {
  originalUrl: string | null;
  result: ExtractionResult;
}

// older backend shapes (a path, a field list) count as not processed yet
export function isCaseReport(value: unknown): value is CaseReport {
  const report = value as CaseReport | null;
  return !!report && typeof report === "object" && !!report.result && typeof report.result.text === "string";
}
