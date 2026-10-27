import { mockDelay } from "../mock";
import type { Lesion } from "../viewer/types";
import type { FieldKey } from "./fields";

export interface QueueEntry {
  studyId: string;
  studyNumber: string;
  studyDate: string;
  uncertainty: number;
}

export interface DoneEntry {
  studyId: string;
  studyNumber: string;
  corrected: boolean;
}

export interface Proposal {
  value: string;
  // model and the regex rules gave different answers
  disagreement?: boolean;
}

export interface ReportPart {
  text: string;
  field?: FieldKey;
}

export interface ReviewCase {
  studyId: string;
  studyNumber: string;
  patientId: string;
  age: number | null;
  studyDate: string;
  description: string;
  uncertainty: number;
  segmentationVersion: string;
  extractionVersion: string | null;
  lesion: Lesion;
  report: ReportPart[] | null;
  proposals: Partial<Record<FieldKey, Proposal>>;
  measurements: { volume: number | null; size: number | null; sizeInReport: number | null };
}

export interface ApprovalPayload {
  mask: "confirmed" | "corrected";
  strokes: number;
  fields: Partial<Record<FieldKey, { value: string; state: "confirmed" | "corrected" }>>;
  editingSeconds: number;
}

const QUEUE: QueueEntry[] = [0.71, 0.66, 0.62, 0.58, 0.55].map((uncertainty, i) => ({
  studyId: `s${i + 1}`,
  studyNumber: String(i + 1).padStart(4, "0"),
  studyDate: `2026-10-${String(26 - i).padStart(2, "0")}`,
  uncertainty,
}));

const REPORT: ReportPart[] = [
  { text: "Treść opisu badania: " },
  { text: "lokalizacja", field: "location" },
  { text: ", " },
  { text: "kształt", field: "shape" },
  { text: ", " },
  { text: "brzegi", field: "margin" },
  { text: ", " },
  { text: "wymiar", field: "size" },
  { text: ", " },
  { text: "krzywa", field: "curve" },
  { text: ", " },
  { text: "BI-RADS", field: "birads" },
  { text: "." },
];

// TODO: no review endpoints yet
export async function fetchQueue(): Promise<{ queue: QueueEntry[]; done: DoneEntry[] }> {
  return mockDelay({
    queue: QUEUE,
    done: [
      { studyId: "s6", studyNumber: "0006", corrected: false },
      { studyId: "s7", studyNumber: "0007", corrected: true },
    ],
  });
}

export async function fetchCase(studyId: string): Promise<ReviewCase> {
  const entry = QUEUE.find((q) => q.studyId === studyId) ?? QUEUE[0];
  const noReport = studyId === "s5";
  return mockDelay({
    studyId: entry.studyId,
    studyNumber: entry.studyNumber,
    patientId: `P-${String(101 + (Number(entry.studyNumber) - 1) * 7).padStart(4, "0")}`,
    age: null,
    studyDate: entry.studyDate,
    description: "MR piersi z kontrastem",
    uncertainty: entry.uncertainty,
    segmentationVersion: "7",
    extractionVersion: noReport ? null : "3",
    lesion: { x: 330, y: 170, slices: [36, 50] },
    report: noReport ? null : REPORT,
    proposals: noReport
      ? {}
      : {
          birads: { value: "4C" },
          location: { value: "KGZ" },
          size: { value: "14" },
          shape: { value: "Nieregularny" },
          margin: { value: "Nieregularne", disagreement: true },
          curve: { value: "Wash-out" },
        },
    measurements: { volume: null, size: null, sizeInReport: null },
  });
}

export async function approveCase(_studyId: string, _payload: ApprovalPayload): Promise<void> {
  return mockDelay(undefined, 400);
}
