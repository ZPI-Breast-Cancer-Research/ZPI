import { api, fetchStudies, sendStudy as apiSendStudy } from "../api";
import { toIsoDate } from "../format";
import { MOCK_API, mockDelay } from "../mock";
import { reviewProgress } from "../review/api";

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
  // ISO date and time the image was verified
  verifiedAt: string | null;
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

const todayAt = (time: string) => `${toIsoDate(new Date())}T${time}`;

const VERIFIED_AT: Record<string, string> = { s6: todayAt("09:12"), s7: todayAt("08:47"), s8: todayAt("10:40") };

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
  verifiedAt: VERIFIED_AT[`s${i + 1}`] ?? null,
}));

// mock rows follow what was approved on the review screen in this session
function withReview(row: StudyRow): StudyRow {
  const { mask, form, done } = reviewProgress(row.id);
  if (!mask && !form) return row;
  return {
    ...row,
    image: mask === "corrected" ? "verified_corrected" : mask ? "verified_unchanged" : row.image,
    report: form ? "verified" : row.report,
    verifiedAt: done ? toIsoDate(new Date()) + "T" + new Date().toTimeString().slice(0, 5) : row.verifiedAt,
  };
}

// the backend uses its own status words (PENDING, COMPLETED…); the list speaks in the stages of the review
const IMAGE_FROM_BACKEND: Record<string, ImageStatus> = {
  PENDING: "queued",
  PROCESSING: "processing",
  COMPLETED: "to_review",
  APPROVED: "verified_unchanged",
  CORRECTED: "verified_corrected",
  REJECTED: "error",
  queued: "queued",
};

const REPORT_FROM_BACKEND: Record<string, ReportStatus> = {
  PENDING: "extracting",
  PROCESSING: "extracting",
  COMPLETED: "to_review",
  APPROVED: "verified",
  CORRECTED: "verified",
  REJECTED: "to_review",
  missing: "missing",
};

export async function listStudies(): Promise<StudyRow[]> {
  if (MOCK_API) return mockDelay(MOCK_ROWS.map(withReview));
  const studies = await fetchStudies();
  // TODO: no study number from the backend yet
  return studies.map((study) => ({
    id: study.orthanc_id,
    number: null,
    patientId: study.patient_id ?? "—",
    studyDate: dicomDateToIso(study.study_date),
    image: IMAGE_FROM_BACKEND[study.segmentation_status] ?? null,
    report: REPORT_FROM_BACKEND[study.extraction_status] ?? null,
    uncertainty: study.uncertainty,
    verifiedAt: null,
  }));
}

export async function listUnassignedReports(): Promise<UnassignedReport[]> {
  if (MOCK_API) {
    return mockDelay([
      { id: "r7", fileName: "opis_7.txt", kind: "text", addedAt: "2026-10-24" },
      { id: "r2", fileName: "skan_2.jpg", kind: "scan", addedAt: "2026-10-22" },
    ]);
  }
  const reports = await api.get<{ id: string; file_name?: string; fileName?: string; kind: UnassignedReport["kind"]; added_at?: string; addedAt?: string }[]>("/api/reports/unassigned/");
  return reports.data.map((report) => ({
    id: report.id,
    fileName: report.file_name ?? report.fileName ?? "",
    kind: report.kind,
    addedAt: report.added_at ?? report.addedAt ?? "",
  }));
}

// TODO: no backend endpoint for the processing steps yet
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

export async function sendStudy(archiveFile?: File, reportFile?: File): Promise<unknown> {
  if (MOCK_API) return mockDelay(null, 400);
  return apiSendStudy(archiveFile, reportFile);
}

export async function attachReport(studyId: string, source: File | string): Promise<void> {
  if (MOCK_API) return mockDelay(undefined, 400);
  const formData = new FormData();
  if (source instanceof File) {
    formData.append("report", source);
    await api.post(`/api/studies/${studyId}/attach-report/`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  } else {
    await api.post(`/api/studies/${studyId}/attach-existing-report/`, {
      report_id: source,
    });
  }
}
