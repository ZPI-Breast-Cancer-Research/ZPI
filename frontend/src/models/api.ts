import { api } from "../api";
import { mockDelay, mockScenario, MOCK_API } from "../mock";
import { record } from "../settings/audit";

// "new": trained, nobody proposed it yet; "retired": was in use before
export type VersionStatus = "training" | "new" | "proposed" | "in_use" | "retired" | "rejected";

// one evaluation of a version; "set" names the data it was scored on
export interface ValidationMetrics {
  set: "cross_validation" | "hospital_test" | "mamamia_test" | null;
  cases: number | null;
  dice: number | null;
  iou: number | null;
  hd95: number | null;
  diceSmall: number | null;
  volumeErrorPct: number | null;
}

// the model's mask against the one the radiologist approved, for a version that was in use
export interface Agreement {
  approved: number | null;
  unchanged: number | null;
  dice: number | null;
  iou: number | null;
  volumeMl: number | null;
}

export interface Person {
  login: string;
  name: string;
}

export interface ModelVersion {
  version: string;
  status: VersionStatus;
  trainedAt: string | null;
  trainingCases: number | null;
  metrics: ValidationMetrics | null;
  // a restored version has more than one
  periods: { from: string; to: string | null }[];
  agreement: Agreement | null;
  proposedBy: Person | null;
  decidedBy: Person | null;
  reason: string | null;
}

// the sentence is built from the rule code in i18n
export interface GateCheck {
  rule: string;
  threshold: number | null;
  value: number | null;
  baseline: number | null;
  studyNumber: string | null;
  // the form field a rule points at, for extraction
  field?: string | null;
  passed: boolean | null;
}

export interface Proposal {
  version: string;
  replaces: string;
  // going back to a version that was in use before
  restore: boolean;
  author: Person & { role: "researcher" | "admin" };
  at: string;
  reason: string;
  // what the version was trained from: the version it starts from and the corrections added
  training: { base: string | null; corrections: number | null } | null;
  gate: GateCheck[] | null;
}

export interface WeakCase {
  studyId: string;
  studyNumber: string;
  dice: number;
}

export interface SegmentationOverview {
  inUse: {
    version: string;
    since: string | null;
    approvedBy: Person | null;
    studies: number | null;
    // studies the pipeline could not segment, by reason
    rejected: { reason: string; count: number }[];
    weakest: WeakCase[] | null;
  } | null;
  // the version to compare with by default: the one used right before the current one
  compareWith: string | null;
  proposal: Proposal | null;
  training: {
    corrections: number | null;
    threshold: number | null;
    window: string | null;
    canStart: boolean;
    run: { version: string; epoch: number | null; epochs: number | null; etaHours: number | null; canStop: boolean } | null;
  } | null;
  versions: ModelVersion[];
}

export function isSegmentationOverview(data: unknown): data is SegmentationOverview {
  return !!data && typeof data === "object" && "inUse" in data && Array.isArray((data as SegmentationOverview).versions);
}

// the shape the backend sends today, read into the new one
interface OldOverview {
  production: { version: string; since: string | null; approvedBy: string } | null;
  previous: string | null;
  correctedShare: { current: number | null; previous: number | null };
  next: { corrections: number; threshold: number; window: string } | null;
  training: { version: string; epoch: number | null; epochs: number | null; etaHours: number | null } | null;
  versions: {
    version: string;
    status: "candidate" | "production" | "archived" | "rejected" | "training";
    from: string | null;
    to: string | null;
    dice: number | null;
    iou: number | null;
    hd95: number | null;
    decidedBy: string | null;
  }[];
}

const OLD_STATUS: Record<OldOverview["versions"][number]["status"], VersionStatus> = {
  candidate: "new",
  production: "in_use",
  archived: "retired",
  rejected: "rejected",
  training: "training",
};

function share(corrected: number | null): number | null {
  return corrected === null ? null : 1 - corrected;
}

function fromOld(old: OldOverview): SegmentationOverview {
  const person = (name: string | null): Person | null => (name ? { login: "", name } : null);
  const inUse = old.production?.version;
  return {
    inUse: old.production && {
      version: old.production.version,
      since: old.production.since,
      approvedBy: person(old.production.approvedBy),
      studies: null,
      rejected: [],
      weakest: null,
    },
    compareWith: old.previous,
    proposal: null,
    training: old.next || old.training
      ? {
          corrections: old.next?.corrections ?? null,
          threshold: old.next?.threshold ?? null,
          window: old.next?.window ?? null,
          canStart: !old.training,
          run: old.training && { ...old.training, canStop: false },
        }
      : null,
    versions: old.versions.map((v) => {
      const unchanged = v.version === inUse ? share(old.correctedShare.current) : v.version === old.previous ? share(old.correctedShare.previous) : null;
      return {
        version: v.version,
        status: OLD_STATUS[v.status],
        trainedAt: null,
        trainingCases: null,
        metrics: v.dice === null && v.iou === null && v.hd95 === null ? null : { set: null, cases: null, dice: v.dice, iou: v.iou, hd95: v.hd95, diceSmall: null, volumeErrorPct: null },
        periods: v.from ? [{ from: v.from, to: v.to }] : [],
        agreement: v.from ? { approved: null, unchanged, dice: null, iou: null, volumeMl: null } : null,
        proposedBy: null,
        decidedBy: person(v.decidedBy),
        reason: null,
      };
    }),
  };
}

const KOWALSKA: Person = { login: "j.kowalska", name: "J. Kowalska" };
const NOWAK: Person = { login: "a.nowak", name: "A. Nowak" };

function cv(dice: number, iou: number, hd95: number, diceSmall: number, volumeErrorPct: number): ValidationMetrics {
  return { set: "cross_validation", cases: 412, dice, iou, hd95, diceSmall, volumeErrorPct };
}

// whoever is signed in, so a mock proposal can be "mine"
function me(): Person & { role: Proposal["author"]["role"] } {
  try {
    const user = JSON.parse(sessionStorage.getItem("maria.user") ?? "") as Person & { role: string };
    if (user.login) return { login: user.login, name: user.name, role: user.role === "admin" ? "admin" : "researcher" };
  } catch {
    // the dev user below
  }
  return { login: "dev", name: "Dev", role: import.meta.env.VITE_SKIP_LOGIN === "admin" ? "admin" : "researcher" };
}

function mockVersions(): ModelVersion[] {
  return [
    {
      version: "1.2.0",
      status: "new",
      trainedAt: "2026-11-07",
      trainingCases: 464,
      metrics: cv(0.829, 0.708, 8.1, 0.68, 12),
      periods: [],
      agreement: null,
      proposedBy: null,
      decidedBy: null,
      reason: null,
    },
    {
      version: "1.1.0",
      status: "in_use",
      trainedAt: "2026-10-14",
      trainingCases: 412,
      metrics: cv(0.812, 0.684, 9.4, 0.61, 14),
      periods: [{ from: "2026-10-18", to: null }],
      agreement: { approved: 168, unchanged: 0.62, dice: 0.87, iou: 0.77, volumeMl: 0.8 },
      proposedBy: KOWALSKA,
      decidedBy: NOWAK,
      reason: "Lepsza na małych zmianach.",
    },
    {
      version: "1.0.0",
      status: "rejected",
      trainedAt: "2026-09-20",
      trainingCases: 398,
      metrics: cv(0.79, 0.653, 10.2, 0.55, 16),
      periods: [],
      agreement: null,
      proposedBy: NOWAK,
      decidedBy: NOWAK,
      reason: "Gorsza na zmianach poniżej 5 ml.",
    },
    {
      version: "0.9.0",
      status: "retired",
      trainedAt: "2026-08-10",
      trainingCases: 380,
      metrics: cv(0.771, 0.627, 11.8, 0.49, 18),
      periods: [
        { from: "2026-08-20", to: "2026-09-18" },
        { from: "2026-09-25", to: "2026-10-18" },
      ],
      agreement: { approved: 94, unchanged: 0.48, dice: 0.8, iou: 0.67, volumeMl: 1.9 },
      proposedBy: NOWAK,
      decidedBy: NOWAK,
      reason: "Model bazowy od zespołu.",
    },
  ];
}

const GATE: GateCheck[] = [
  { rule: "dice_not_lower", threshold: null, value: 0.829, baseline: 0.812, studyNumber: null, passed: true },
  { rule: "no_large_drop", threshold: 0.1, value: 0.08, baseline: null, studyNumber: "0019", passed: true },
];

// ?mock=proposal (a researcher's proposal waits), ?mock=mine (your own), ?mock=training, ?mock=empty (nothing computed yet)
let mockState: SegmentationOverview | null = null;

function mockOverview(): SegmentationOverview {
  const scenario = mockScenario();
  if (scenario === "empty") {
    return {
      inUse: { version: "1.1.0", since: "2026-10-18", approvedBy: NOWAK, studies: null, rejected: [], weakest: null },
      compareWith: null,
      proposal: null,
      training: null,
      versions: mockVersions()
        .filter((v) => v.status === "in_use")
        .map((v) => ({ ...v, metrics: null, agreement: { approved: 0, unchanged: null, dice: null, iou: null, volumeMl: null }, trainingCases: null })),
    };
  }

  const versions = mockVersions();
  const proposed = scenario === "proposal" || scenario === "mine";
  if (proposed) versions[0] = { ...versions[0], status: "proposed", proposedBy: scenario === "mine" ? me() : KOWALSKA };
  if (scenario === "training") versions.unshift({ ...versions[0], version: "1.3.0", status: "training", trainedAt: null, metrics: null, trainingCases: null });

  return {
    inUse: {
      version: "1.1.0",
      since: "2026-10-18",
      approvedBy: NOWAK,
      studies: 214,
      rejected: [{ reason: "incomplete", count: 3 }],
      weakest: [
        { studyId: "s42", studyNumber: "0042", dice: 0.31 },
        { studyId: "s107", studyNumber: "0107", dice: 0.44 },
        { studyId: "s63", studyNumber: "0063", dice: 0.52 },
      ],
    },
    compareWith: "0.9.0",
    proposal: proposed
      ? {
          version: "1.2.0",
          replaces: "1.1.0",
          author: scenario === "mine" ? me() : { ...KOWALSKA, role: "researcher" },
          restore: false,
          at: "2026-11-07",
          reason: "Lepiej obrysowuje małe zmiany, które w 1.1.0 lekarze najczęściej poprawiali.",
          training: { base: "1.1.0", corrections: 52 },
          gate: GATE,
        }
      : null,
    training: {
      corrections: 18,
      threshold: 50,
      window: "2026-11-13T02:00",
      canStart: scenario !== "training",
      run: scenario === "training" ? { version: "1.3.0", epoch: 31, epochs: 50, etaHours: 2, canStop: true } : null,
    },
    versions,
  };
}

export async function fetchSegmentation(): Promise<SegmentationOverview> {
  if (MOCK_API) {
    mockState ??= mockOverview();
    return mockDelay(structuredClone(mockState));
  }
  const { data } = await api.get<SegmentationOverview | OldOverview>("/api/models/segmentation/");
  return isSegmentationOverview(data) ? data : fromOld(data);
}

// the gate a version would face, before anyone proposes it
export async function fetchGate(version: string): Promise<GateCheck[] | null> {
  if (MOCK_API) return mockDelay(version === "1.2.0" ? GATE : null);
  const { data } = await api.get<GateCheck[] | null>(`/api/models/${version}/gate/`);
  return data;
}

// mock decisions update the mock state
function today() {
  return new Date().toISOString().slice(0, 10);
}

function putInUse(state: SegmentationOverview, version: string, reason: string | null) {
  const since = today();
  for (const v of state.versions) {
    if (v.status === "in_use") {
      v.status = "retired";
      v.periods = v.periods.map((p) => (p.to ? p : { ...p, to: since }));
    }
    if (v.version === version) {
      v.status = "in_use";
      v.periods = [...v.periods, { from: since, to: null }];
      const { login, name } = me();
      v.decidedBy = { login, name };
      v.agreement ??= { approved: 0, unchanged: null, dice: null, iou: null, volumeMl: null };
      // an admin's own change: no proposal, their reason instead
      v.reason = state.proposal?.reason ?? reason;
      if (!state.proposal) v.proposedBy = { login, name };
    }
  }
  if (state.inUse) state.compareWith = state.inUse.version;
  const { login, name } = me();
  state.inUse = { version, since, approvedBy: { login, name }, studies: 0, rejected: [], weakest: null };
  state.proposal = null;
}

function updateMock(change: (state: SegmentationOverview) => void) {
  mockState ??= mockOverview();
  change(mockState);
}

// reason only for an admin's own change
export async function promote(version: string, reason: string | null = null): Promise<string> {
  if (MOCK_API) {
    updateMock((state) => putInUse(state, version, reason));
    record("model_promoted", version, reason);
    return mockDelay(version, 400);
  }
  const { data } = await api.post<string>(`/api/models/${version}/promote/`, { reason });
  record("model_promoted", version, reason);
  return data;
}

export async function reject(version: string, reason: string): Promise<string> {
  if (MOCK_API) {
    updateMock((state) => {
      const v = state.versions.find((item) => item.version === version);
      const { login, name } = me();
      // a rejected restore goes back to being a retired version
      if (v) Object.assign(v, { status: state.proposal?.restore ? "retired" : "rejected", decidedBy: { login, name }, reason });
      state.proposal = null;
    });
    record("model_rejected", version, reason);
    return mockDelay(version, 400);
  }
  const { data } = await api.post<string>(`/api/models/${version}/reject/`, { reason });
  record("model_rejected", version, reason);
  return data;
}

export async function rollback(version: string, reason: string | null = null): Promise<string> {
  if (MOCK_API) {
    updateMock((state) => putInUse(state, version, reason));
    record("model_rolled_back", version, reason);
    return mockDelay(version, 400);
  }
  const { data } = await api.post<string>(`/api/models/${version}/rollback/`, { reason });
  record("model_rolled_back", version, reason);
  return data;
}

export async function propose(version: string, reason: string, restore: boolean): Promise<string> {
  if (MOCK_API) {
    updateMock((state) => {
      const v = state.versions.find((item) => item.version === version);
      if (!v || !state.inUse) return;
      const author = me();
      // a restored version keeps who brought it in the first time
      v.status = "proposed";
      if (!restore) Object.assign(v, { proposedBy: { login: author.login, name: author.name }, reason });
      state.proposal = {
        version,
        replaces: state.inUse.version,
        restore,
        author,
        at: today(),
        reason,
        training: restore ? null : { base: state.inUse.version, corrections: 52 },
        gate: version === "1.2.0" ? GATE : null,
      };
    });
    record("model_proposed", version, reason);
    return mockDelay(version, 400);
  }
  const { data } = await api.post<string>("/api/models/segmentation/proposals/", { version, reason, restore });
  record("model_proposed", version, reason);
  return data;
}

export async function withdraw(version: string): Promise<string> {
  if (MOCK_API) {
    updateMock((state) => {
      const v = state.versions.find((item) => item.version === version);
      if (v) Object.assign(v, state.proposal?.restore ? { status: "retired" } : { status: "new", proposedBy: null, reason: null });
      state.proposal = null;
    });
    record("proposal_withdrawn", version);
    return mockDelay(version, 400);
  }
  const { data } = await api.post<string>(`/api/models/${version}/withdraw/`);
  record("proposal_withdrawn", version);
  return data;
}

export async function startTraining(): Promise<void> {
  if (MOCK_API) {
    record("training_started", "");
    return mockDelay(undefined, 400);
  }
  await api.post("/api/models/training/start/");
  record("training_started", "");
}
export async function stopTraining(): Promise<void> {
  if (MOCK_API) {
    updateMock((state) => {
      if (state.training) Object.assign(state.training, { run: null, canStart: true });
      state.versions = state.versions.filter((v) => v.status !== "training");
    });
    record("training_stopped", "");
    return mockDelay(undefined, 400);
  }
  await api.post("/api/models/training/stop/");
  record("training_stopped", "");
}
