import { api, handleApiError } from "../api";
import { mockDelay, mockScenario, mockStudyUid, MOCK_API } from "../mock";
import type { FieldAnswers } from "../review/api";
import { isCaseReport, type CaseReport, type Extraction } from "../review/extraction";
import type { MaskSource } from "../viewer/types";

export interface OverviewReport {
  source: CaseReport;
  accepted: Extraction;
  lesions: Record<number, FieldAnswers>;
  onImage: number | null;
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
  masks: { approved: MaskSource; model: MaskSource };
  mask: { corrected: boolean; version: number; date: string; by: string };
  measurements: { volume: number | null; dimensions: [number, number, number] | null; intensity: number | null };
  report: OverviewReport | null;
  reportPending?: boolean;
  comparison: { feature: "largestSize" | "quadrant"; fromMask: string | null; fromReport: string | null; match: boolean | null }[];
  verification: { by: string; date: string; editingSeconds: number; segmentationVersion: string; extractionVersion: string | null };
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
      masks: {
        approved: { center: [0.69, 0.585, 0.53], radius: [13, 11, 12] },
        model: { center: [0.685, 0.58, 0.53], radius: [11, 9, 10] },
      },
      mask: { corrected: true, version: 1, date: "2026-10-21", by: "Użytkownik" },
      measurements: { volume: null, dimensions: null, intensity: null },
      report: null,
      comparison: [
        { feature: "largestSize", fromMask: null, fromReport: "16 mm", match: null },
        { feature: "quadrant", fromMask: null, fromReport: "KGZ", match: null },
      ],
      verification: { by: "Użytkownik", date: "2026-10-21", editingSeconds: 74, segmentationVersion: "7", extractionVersion: noReport ? null : "3" },
    });
  }
  try {
    const { data } = await api.get<Overview>(`/api/review/cases/${encodeURIComponent(studyId)}/review-overview/`);
    const ready = !!data.report && isCaseReport(data.report.source);
    return { ...data, report: ready ? data.report : null, reportPending: !ready && !!data.report };
  } catch (error) {
    handleApiError(error);
  }
}
