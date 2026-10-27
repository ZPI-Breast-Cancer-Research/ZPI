// fields from the UI mockup; the extractor (workers/extraction/schema.py) returns a different, MMG/USG-based
// structure, so this list changes once the team settles MRI vs MMG/USG reports
export interface FieldDef {
  key: "birads" | "location" | "size" | "shape" | "margin" | "curve";
  label: string;
  options?: string[];
  unit?: string;
}

export const FIELDS: FieldDef[] = [
  { key: "birads", label: "BI-RADS", options: ["2", "3", "4A", "4B", "4C", "5", "6"] },
  { key: "location", label: "Lokalizacja", options: ["KGZ", "KGW", "KDZ", "KDW"] },
  { key: "size", label: "Wymiar", unit: "mm" },
  { key: "shape", label: "Kształt", options: ["Owalny", "Okrągły", "Nieregularny"] },
  { key: "margin", label: "Brzegi", options: ["Gładkie", "Nieregularne", "Spikularne"] },
  { key: "curve", label: "Krzywa", options: ["Narastająca", "Plateau", "Wash-out"] },
];

export type FieldKey = FieldDef["key"];
