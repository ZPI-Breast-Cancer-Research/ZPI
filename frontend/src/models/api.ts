import { mockDelay, mockScenario } from "../mock";

export type VersionStatus = "candidate" | "production" | "archived" | "rejected" | "training";

export interface ModelVersion {
  version: string;
  status: VersionStatus;
  alias: "@candidate" | "@production" | null;
  from: string | null;
  to: string | null;
  dice: number | null;
  hd95: number | null;
  diceMamaMia: number | null;
  decision: "promoted" | "replaced" | "rejected_gate" | "rejected" | "pending" | "baseline";
  decidedBy: string | null;
  canRestore: boolean;
}

export interface GateRule {
  rule: "better_hospital" | "not_worse_mamamia" | "no_large_drop";
  passed: boolean;
}

export interface DiffCase {
  studyId: string;
  studyNumber: string;
  label: "biggest_gain" | "gain" | "biggest_drop" | "drop";
  current: number | null;
  candidate: number | null;
}

export interface SegmentationOverview {
  production: { version: string; since: string; approvedBy: string };
  previous: string | null;
  correctedShare: { current: number; previous: number | null };
  editTime: { current: number; previous: number | null };
  weeklyCorrected: { week: string; share: number; versionChange?: string }[];
  next: { corrections: number; threshold: number; window: string } | null;
  lastRun: { date: string; version: string; outcome: "rejected_gate" | "promoted" } | null;
  training: { version: string; epoch: number; epochs: number; etaHours: number } | null;
  candidate: { version: string; gate: GateRule[]; cases: DiffCase[]; trainingData: number } | null;
  versions: ModelVersion[];
}

export interface ExtractionOverview {
  version: string;
  since: string;
  fields: { field: string; f1: number | null; correctedShare: number }[];
  examplePool: number;
}

const WEEKS = ["2026-08-31", "2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"];

// Dice/HD95/F1 come from MLflow, keep them null here
export async function fetchSegmentation(): Promise<SegmentationOverview> {
  const scenario = mockScenario();
  const candidate = scenario === "candidate";
  const training = scenario === "training";

  const versions: ModelVersion[] = [
    { version: "7", status: "production", alias: "@production", from: "2026-10-05", to: null, dice: null, hd95: null, diceMamaMia: null, decision: "promoted", decidedBy: "Użytkownik", canRestore: false },
    { version: "6", status: "archived", alias: null, from: "2026-09-01", to: "2026-10-05", dice: null, hd95: null, diceMamaMia: null, decision: "replaced", decidedBy: null, canRestore: true },
    { version: "5", status: "rejected", alias: null, from: null, to: null, dice: null, hd95: null, diceMamaMia: null, decision: "rejected_gate", decidedBy: null, canRestore: false },
    { version: "bazowa", status: "archived", alias: null, from: "2026-06-15", to: "2026-09-01", dice: null, hd95: null, diceMamaMia: null, decision: "baseline", decidedBy: null, canRestore: true },
  ];
  if (candidate) {
    versions.unshift({ version: "8", status: "candidate", alias: "@candidate", from: null, to: null, dice: null, hd95: null, diceMamaMia: null, decision: "pending", decidedBy: null, canRestore: false });
  }

  return mockDelay({
    production: { version: "7", since: "2026-10-05", approvedBy: "Użytkownik" },
    previous: "6",
    correctedShare: { current: 0.31, previous: 0.38 },
    editTime: { current: 74, previous: 92 },
    weeklyCorrected: [0.4, 0.37, 0.39, 0.36, 0.38, 0.33, 0.31, 0.3].map((share, i) => ({
      week: WEEKS[i],
      share,
      versionChange: i === 5 ? "7" : undefined,
    })),
    next: candidate || training ? null : { corrections: 32, threshold: 50, window: "2026-10-27T02:00" },
    lastRun: { date: "2026-10-19", version: "5", outcome: "rejected_gate" },
    training: training ? { version: "8", epoch: 31, epochs: 50, etaHours: 2 } : null,
    candidate: candidate
      ? {
          version: "8",
          trainingData: 50,
          gate: [
            { rule: "better_hospital", passed: true },
            { rule: "not_worse_mamamia", passed: true },
            { rule: "no_large_drop", passed: true },
          ],
          cases: [
            { studyId: "t31", studyNumber: "0031", label: "biggest_gain", current: null, candidate: null },
            { studyId: "t44", studyNumber: "0044", label: "gain", current: null, candidate: null },
            { studyId: "t52", studyNumber: "0052", label: "biggest_drop", current: null, candidate: null },
            { studyId: "t60", studyNumber: "0060", label: "drop", current: null, candidate: null },
          ],
        }
      : null,
    versions,
  });
}

export async function fetchExtraction(): Promise<ExtractionOverview> {
  return mockDelay({
    version: "3",
    since: "2026-09-20",
    examplePool: 46,
    fields: [
      { field: "BI-RADS", f1: null, correctedShare: 0.06 },
      { field: "Lokalizacja", f1: null, correctedShare: 0.09 },
      { field: "Wymiar", f1: null, correctedShare: 0.12 },
      { field: "Kształt", f1: null, correctedShare: 0.14 },
      { field: "Brzegi", f1: null, correctedShare: 0.27 },
      { field: "Krzywa", f1: null, correctedShare: 0.11 },
    ],
  });
}

// TODO: wire to POST /models/{id}/promote, /reject, /rollback once they exist
export async function promote(version: string): Promise<string> {
  return mockDelay(version, 400);
}

export async function reject(version: string, _reason: string): Promise<string> {
  return mockDelay(version, 400);
}

export async function rollback(version: string): Promise<string> {
  return mockDelay(version, 400);
}

export async function startTraining(): Promise<void> {
  return mockDelay(undefined, 400);
}
