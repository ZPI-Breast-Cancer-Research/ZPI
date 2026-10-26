import { mockDelay } from "../mock";

export interface QueueItem {
  studyId: string;
  studyNumber: string;
  patientId: string;
  studyDate: string;
  uncertainty: number;
}

export type AttentionKind = "processing_error" | "model_candidate" | "missing_report";

export interface AttentionItem {
  kind: AttentionKind;
  subject: string;
  count?: number;
  href: string;
}

export type ProcessingStage = "conversion" | "segmentation" | "extraction";

export interface ProcessingItem {
  studyNumber: string;
  stage: ProcessingStage | null;
  state: "running" | "queued";
}

export interface VerifiedDay {
  date: string;
  unchanged: number;
  corrected: number;
}

export interface Dashboard {
  toReview: number;
  processing: number;
  verifiedToday: number;
  queue: QueueItem[];
  attention: AttentionItem[];
  inProgress: ProcessingItem[];
  verifiedLastWeek: VerifiedDay[];
}

// fake data until the backend has a dashboard endpoint
const MOCK: Dashboard = {
  toReview: 14,
  processing: 3,
  verifiedToday: 6,
  queue: [0.71, 0.66, 0.62, 0.58, 0.55, 0.51, 0.47, 0.44, 0.4, 0.37, 0.33, 0.3, 0.26, 0.22].map((uncertainty, i) => ({
    studyId: `s${i + 1}`,
    studyNumber: String(i + 1).padStart(4, "0"),
    patientId: `P-${String(101 + i * 7).padStart(4, "0")}`,
    studyDate: `2026-10-${String(26 - (i % 9)).padStart(2, "0")}`,
    uncertainty,
  })),
  attention: [
    { kind: "processing_error", subject: "0018", href: "/badania" },
    { kind: "model_candidate", subject: "segmentation", href: "/modele" },
    { kind: "missing_report", subject: "", count: 4, href: "/badania" },
  ],
  inProgress: [
    { studyNumber: "0015", stage: "segmentation", state: "running" },
    { studyNumber: "0016", stage: "extraction", state: "running" },
    { studyNumber: "0017", stage: null, state: "queued" },
  ],
  verifiedLastWeek: [
    { date: "2026-10-20", unchanged: 5, corrected: 2 },
    { date: "2026-10-21", unchanged: 7, corrected: 3 },
    { date: "2026-10-22", unchanged: 6, corrected: 2 },
    { date: "2026-10-23", unchanged: 8, corrected: 3 },
    { date: "2026-10-24", unchanged: 6, corrected: 3 },
    { date: "2026-10-25", unchanged: 4, corrected: 2 },
    { date: "2026-10-26", unchanged: 4, corrected: 2 },
  ],
};

export async function fetchDashboard(): Promise<Dashboard> {
  return mockDelay(MOCK);
}
