import { mockDelay, mockScenario, mockStudyUid, MOCK_API } from "../mock";
import type { FieldKey } from "../review/fields";
import type { SegRef } from "../viewer/types";
import {api, handleApiError} from "../api"

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
  report: { field: FieldKey; value: string; corrected: boolean }[] | null;
  comparison: { feature: "largestSize" | "quadrant"; fromMask: string | null; fromReport: string | null; match: boolean | null }[];
  verification: { by: string; date: string; editingSeconds: number; segmentationVersion: string; extractionVersion: string | null };
}

// TODO: no lesion overview endpoint yet; ?mock=saving / ?mock=no-report preview the other states
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
      report: noReport
        ? null
        : [
            { field: "birads", value: "4C", corrected: false },
            { field: "location", value: "KGZ", corrected: false },
            { field: "size", value: "14 mm", corrected: false },
            { field: "shape", value: "Owalny", corrected: true },
            { field: "margin", value: "Nieregularne", corrected: false },
            { field: "curve", value: "Plateau", corrected: true },
          ],
      comparison: [
        { feature: "largestSize", fromMask: null, fromReport: "14 mm", match: null },
        { feature: "quadrant", fromMask: null, fromReport: "KGZ", match: null },
      ],
      verification: { by: "Użytkownik", date: "2026-10-21", editingSeconds: 74, segmentationVersion: "7", extractionVersion: noReport ? null : "3" },
    });
  }
  try {
    const { data } = await api.get<Overview>(`/api/review/cases/${encodeURIComponent(studyId)}/review-overview/`);
    return data;
  } catch (error) {
    handleApiError(error);
  }

}
