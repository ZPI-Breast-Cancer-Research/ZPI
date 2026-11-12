import { api, handleApiError } from "../api";
import { mockDelay, mockScenario, mockStudyUid, MOCK_API } from "../mock";
import type { FieldKey } from "../review/fields";
import type { SegRef } from "../viewer/types";
import {api, handleApiError} from "../api"
import type { FieldAnswers } from "../review/api";
import { isCaseReport, type CaseReport, type Extraction } from "../review/extraction";
import type { MaskSource } from "../viewer/types";

export interface OverviewReport {
  source: CaseReport;
  accepted: Extraction;
  lesions: Record<number, FieldAnswers>;
}

export interface Overview {
  studyId: string;
  studyNumber: string;
  patientId: string;
  age: number | null;
  studyDate: string;
  description: string;
  status: "verified" | "saving";
  studyUid: string | null;
  // approved mask and the model's original one
  masks: { approved: SegRef | null; model: SegRef | null };
  mask: { corrected: boolean; version: number; date: string; by: string };
  measurements: { volume: number | null; dimensions: [number, number, number] | null; intensity: number | null };
  report: OverviewReport | null;
  reportPending?: boolean;
  comparison: { feature: "largestSize" | "quadrant"; fromMask: string | null; fromReport: string | null; match: boolean | null }[];
  verification: {
    by: string;
    date: string;
    // the model's mask against the approved one
    agreement: { dice: number | null; iou: number | null; volumeMl: number | null } | null;
    segmentationVersion: string;
    extractionVersion: string | null;
  };
}

// ?mock=saving / ?mock=no-report preview the other states
export async function fetchOverview(studyId: string): Promise<Overview> {
  if(MOCK_API){
    const scenario = mockScenario();
    const saving = scenario === "saving";
    const noReport = scenario === "no-report";
    const studyUid = await mockStudyUid(0);
    return mockDelay({
      studyId,
      studyNumber: "0007",
      patientId: "P-0143",
      age: null,
      studyDate: "2026-10-20",
      description: "MR piersi z kontrastem",
      status: saving ? "saving" : "verified",
      studyUid,
      // mock studies are not in Orthanc, so there is no SEG to point to
      masks: { approved: null, model: null },
      mask: { corrected: true, version: 1, date: "2026-10-21", by: "Użytkownik" },
      measurements: { volume: null, dimensions: null, intensity: null },
      report: null,
      comparison: [
        { feature: "largestSize", fromMask: null, fromReport: "16 mm", match: null },
        { feature: "quadrant", fromMask: null, fromReport: "KGZ", match: null },
      ],
      verification: {
        by: "Użytkownik",
        date: "2026-10-21",
        agreement: { dice: 0.87, iou: 0.77, volumeMl: 1.2 },
        segmentationVersion: "7",
        extractionVersion: noReport ? null : "3",
      },
    });
  }
  try {
    const { data } = await api.get<Overview>(`/api/review/cases/${encodeURIComponent(studyId)}/review-overview/`);
    const ready = !!data.report && isCaseReport(data.report.source);
    return {
      ...data,
      report: ready ? data.report : null,
      reportPending: !ready && !!data.report,
      verification: { ...data.verification, agreement: data.verification.agreement ?? null },
    };
  } catch (error) {
    handleApiError(error);
  }
}
