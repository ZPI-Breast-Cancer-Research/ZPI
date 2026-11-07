import { api } from "../api";
import { mockDelay, mockStudyUid, MOCK_API } from "../mock";
import { record } from "../settings/audit";
import type { MaskSource } from "../viewer/types";
import type { FieldKey } from "./fields";

export interface QueueEntry {
  studyId: string;
  studyNumber: string;
  studyDate: string;
  uncertainty: number;
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
  studyUid: string | null;
  mask: MaskSource;
  report: ReportPart[] | null;
  proposals: Partial<Record<FieldKey, Proposal>>;
  measurements: { volume: number | null; size: number | null; sizeInReport: number | null };
  // the mask was approved on its own; the case still waits for the form
  maskApproved: "confirmed" | "corrected" | null;
}

export interface ApprovalPayload {
  mask: "confirmed" | "corrected";
  edits: number;
  fields: Partial<Record<FieldKey, { value: string; state: "confirmed" | "corrected" }>>;
  editingSeconds: number;
}

// --- MOCK DATA (dla trybu MOCK_API) ---
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

const MOCK_MASK: MaskSource = { center: [0.69, 0.585, 0.53], radius: [11, 9, 10] };

const approved = new Set<string>();
const masksApproved = new Map<string, "confirmed" | "corrected">();
const formsApproved = new Set<string>();

function label(studyId: string) {
  return `#${QUEUE.find((entry) => entry.studyId === studyId)?.studyNumber ?? studyId}`;
}

export function reviewProgress(studyId: string) {
  if (MOCK_API) {
    return { mask: masksApproved.get(studyId) ?? null, form: formsApproved.has(studyId), done: approved.has(studyId) };
  }
  return { mask: null, form: false, done: false };
}

// --- GŁÓWNE FUNKCJE API (KOMUNIKACJA Z DJANGO) ---

// least certain first, the order verification follows
export async function fetchQueue(): Promise<QueueEntry[]> {
  if (MOCK_API) {
    return mockDelay(QUEUE.filter((entry) => !approved.has(entry.studyId)).sort((a, b) => b.uncertainty - a.uncertainty));
  }
  const { data } = await api.get<QueueEntry[]>("/api/review/queue/");
  return data;
}

export async function fetchCase(studyId: string): Promise<ReviewCase> {
  if (MOCK_API) {
    const index = Math.max(0, QUEUE.findIndex((q) => q.studyId === studyId));
    const entry = QUEUE[index];
    const studyUid = await mockStudyUid(index);
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
      studyUid,
      mask: MOCK_MASK,
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
      maskApproved: masksApproved.get(studyId) ?? null,
    });
  }
  const { data } = await api.get<ReviewCase>(`/api/review/cases/${studyId}/`);
  return data;
}

export async function approveCase(studyId: string, payload: ApprovalPayload): Promise<void> {
  if (MOCK_API) {
    approved.add(studyId);
    if (!masksApproved.has(studyId)) masksApproved.set(studyId, payload.mask);
    formsApproved.add(studyId);
    record("mask_approved", label(studyId));
    record("form_approved", label(studyId));
    return mockDelay(undefined, 400);
  }
  await api.post(`/api/review/cases/${studyId}/approve/`, payload);
  record("mask_approved", `#${studyId}`);
  record("form_approved", `#${studyId}`);
}

// the mask on its own; the case stays in the queue for its form
export async function approveMask(studyId: string, payload: Pick<ApprovalPayload, "mask" | "edits">): Promise<void> {
  if (MOCK_API) {
    masksApproved.set(studyId, payload.mask);
    record("mask_approved", label(studyId));
    return mockDelay(undefined, 300);
  }
  await api.post(`/api/review/cases/${studyId}/approve-mask/`, payload);
  record("mask_approved", `#${studyId}`);
}

// back in the queue when its mask approval is taken back
export async function reopenCase(studyId: string): Promise<void> {
  if (MOCK_API) {
    approved.delete(studyId);
    return mockDelay(undefined, 200);
  }
  await api.post(`/api/review/cases/${studyId}/reopen/`);
}

export async function unapproveMask(studyId: string): Promise<void> {
  if (MOCK_API) {
    masksApproved.delete(studyId);
    record("mask_unapproved", label(studyId));
    return mockDelay(undefined, 200);
  }
  await api.post(`/api/review/cases/${studyId}/unapprove-mask/`);
  record("mask_unapproved", `#${studyId}`);
}

// called when every field is confirmed or corrected; the form needs no button of its own
export async function approveForm(studyId: string, fields: ApprovalPayload["fields"]): Promise<void> {
  if (MOCK_API) {
    formsApproved.add(studyId);
    record("form_approved", label(studyId));
    return mockDelay(undefined, 200);
  }
  await api.post(`/api/review/cases/${studyId}/approve-form/`, { fields });
  record("form_approved", `#${studyId}`);
}

export async function unapproveForm(studyId: string): Promise<void> {
  if (MOCK_API) {
    formsApproved.delete(studyId);
    record("form_unapproved", label(studyId));
    return mockDelay(undefined, 200);
  }
  await api.post(`/api/review/cases/${studyId}/unapprove-form/`);
  record("form_unapproved", `#${studyId}`);
}