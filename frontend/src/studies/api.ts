import { fetchStudies } from "../api";
import { MOCK_API, mockDelay } from "../mock";

export type ImageStatus =
  | "queued"
  | "processing"
  | "error"
  | "to_review"
  | "saving"
  | "verified_unchanged"
  | "verified_corrected";

export type ReportStatus = "missing" | "extracting" | "ready" | "to_review" | "verified";

export interface StudyRow {
  id: string;
  number: string | null;
  patientId: string;
  studyDate: string | null;
  image: ImageStatus | null;
  report: ReportStatus | null;
  uncertainty: number | null;
  viewerUrl: string | null;
}

export interface UnassignedReport {
  id: string;
  fileName: string;
  kind: "text" | "scan";
  addedAt: string;
}

export type StepState = "done" | "running" | "waiting" | "waiting_report" | "error";

export interface ProcessingStep {
  key: "pacs" | "convert" | "segmentation" | "extraction";
  state: StepState;
}

function dicomDateToIso(value: string | null): string | null {
  return value && /^\d{8}$/.test(value) ? `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}` : null;
}

const MOCK_ROWS: StudyRow[] = (
  [
    ["processing", "missing", null],
    ["queued", "extracting", null],
    ["error", "ready", null],
    ["to_review", "to_review", 0.58],
    ["to_review", "missing", 0.51],
    ["verified_unchanged", "to_review", 0.44],
    ["verified_corrected", "verified", 0.4],
    ["saving", "missing", 0.37],
  ] as [ImageStatus, ReportStatus, number | null][]
).map(([image, report, uncertainty], i) => ({
  id: `s${i + 1}`,
  number: String(i + 1).padStart(4, "0"),
  patientId: `P-${String(101 + i * 7).padStart(4, "0")}`,
  studyDate: `2026-10-${String(26 - i).padStart(2, "0")}`,
  image,
  report,
  uncertainty,
  viewerUrl: null,
}));

// the backend doesn't return image/report statuses yet, so those stay empty for real data
export async function listStudies(): Promise<StudyRow[]> {
  if (MOCK_API) return mockDelay(MOCK_ROWS);
  const studies = await fetchStudies();
  return studies.map((study) => ({
    id: study.orthanc_id,
    number: null,
    patientId: study.patient_id ?? "—",
    studyDate: dicomDateToIso(study.study_date),
    image: null,
    report: null,
    uncertainty: null,
    viewerUrl: study.viewer_url,
  }));
}

// TODO: no backend endpoints for the rest of this file yet
export async function listUnassignedReports(): Promise<UnassignedReport[]> {
  return mockDelay([
    { id: "r7", fileName: "opis_7.txt", kind: "text", addedAt: "2026-10-24" },
    { id: "r2", fileName: "skan_2.jpg", kind: "scan", addedAt: "2026-10-22" },
  ]);
}

export async function getProcessingSteps(study: StudyRow): Promise<ProcessingStep[]> {
  const done = study.image !== "queued" && study.image !== "processing" && study.image !== "error";
  return mockDelay([
    { key: "pacs", state: "done" },
    { key: "convert", state: study.image === "queued" ? "waiting" : study.image === "error" ? "error" : "done" },
    { key: "segmentation", state: done ? "done" : study.image === "processing" ? "running" : "waiting" },
    {
      key: "extraction",
      state: study.report === "missing" ? "waiting_report" : study.report === "extracting" ? "running" : "done",
    },
  ]);
}

export async function sendStudies(count: number): Promise<number> {
  return mockDelay(count, 400);
}

export async function attachReport(_studyId: string, _source: File | string): Promise<void> {
  return mockDelay(undefined, 400);
}
