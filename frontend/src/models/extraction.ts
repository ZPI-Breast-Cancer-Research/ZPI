import { api, request } from "../api";
import { mockDelay, mockScenario, MOCK_API } from "../mock";
import type { Extraction, WireBiRads, WireLesion, WireObservation, WireSide } from "../review/extraction";
import { record } from "../settings/audit";
import type { Person, VersionStatus } from "./api";

// One extraction version is one configuration: the language model, the prompt, structured output
// and the few-shot examples (backend module_version, module "ext"). A researcher changes a draft,
// proposes it, an admin puts it in use.
export interface ExtractionVersion {
  version: string;
  status: VersionStatus;
  periods: { from: string; to: string | null }[];
  // lesions found on the test set (F1); null until the version is evaluated
  f1: number | null;
  llmModel: string;
  promptVersion: string;
  structuredOutput: boolean;
  examples: number;
  // a draft: the only status in which the configuration may change
  editable: boolean;
  proposedBy: Person | null;
  proposedAt: string | null;
  decidedBy: Person | null;
  reason: string | null;
  // the proposal brings back an archived version
  restore: boolean;
}

export interface FieldScore {
  // a form field key; an older backend sends a label
  field: string;
  // share of test reports where the model got the field right
  accuracy: number | null;
  // share of verified reports where the doctor changed it
  corrected: number | null;
}

export interface ExtractionProposal {
  version: ExtractionVersion;
  // the version in use it would replace
  replaces: ExtractionVersion | null;
  author: Person;
  at: string | null;
  reason: string;
}

export interface ExtractionOverview {
  inUse: {
    version: string;
    model: string | null;
    since: string | null;
    approvedBy: Person | null;
    verified: number | null;
    failed: number | null;
    corrected: number | null;
  } | null;
  // test set size
  testReports: number | null;
  fields: FieldScore[];
  proposal: ExtractionProposal | null;
  versions: ExtractionVersion[];
}

// what the backend sends for one version (backend/mlops/extraction_versions.py _payload)
export interface VersionConfig {
  version: string;
  name: string;
  status: string;
  llmModel: string;
  promptVersion: string;
  structuredOutput: boolean;
  fewShotExamples: { report: string; output: Extraction; report_id?: number }[];
  editable: boolean;
}

export interface FewShotExample {
  id: string;
  title: string;
  report: string;
  output: Extraction;
  // not in the set in use
  isNew: boolean;
}

// what a draft may change (PATCH extraction/versions/<v>/)
export interface DraftChanges {
  llm_model?: string;
  structured_output?: boolean;
  few_shot_examples?: VersionConfig["fewShotExamples"];
}

interface BackendVersion {
  version: string;
  status: string;
  createdAt: string | null;
  activatedAt: string | null;
  llmModel?: string;
  promptVersion?: string;
  structuredOutput?: boolean;
  fewShot?: number;
  editable?: boolean;
  periods?: { from: string | null; to: string | null }[];
  f1?: number | null;
  proposedBy?: Person | null;
  proposedAt?: string | null;
  decidedBy?: Person | null;
  reason?: string | null;
  restore?: boolean;
}

interface BackendExtractionOverview {
  version: string | null;
  llmModel?: string | null;
  approvedBy?: Person | null;
  since: string | null;
  examplePool: number;
  verifiedDescriptions: number;
  failedDescriptions: number;
  correctedDescriptions: number;
  models: BackendVersion[];
  fields: {
    field: string;
    f1: number | null;
    correctedShare: number | null;
  }[];
}

const STATUS: Record<string, VersionStatus> = {
  production: "in_use",
  archived: "retired",
  rejected: "rejected",
  candidate: "proposed",
  training: "training",
  new: "new",
};

function versionFromBackend(v: BackendVersion): ExtractionVersion {
  const periods = (v.periods ?? (v.activatedAt ? [{ from: v.activatedAt, to: null }] : []))
    .filter((p): p is { from: string; to: string | null } => !!p.from);
  const status = STATUS[v.status] ?? "new";
  return {
    version: v.version,
    status,
    periods,
    f1: v.f1 ?? null,
    llmModel: v.llmModel ?? "",
    promptVersion: v.promptVersion ?? "",
    structuredOutput: v.structuredOutput ?? true,
    examples: v.fewShot ?? 0,
    editable: v.editable ?? status === "new",
    proposedBy: v.proposedBy ?? null,
    proposedAt: v.proposedAt ?? null,
    decidedBy: v.decidedBy ?? null,
    reason: v.reason ?? null,
    restore: v.restore ?? false,
  };
}

function proposalOf(versions: ExtractionVersion[]): ExtractionProposal | null {
  const proposed = versions.find((v) => v.status === "proposed");
  if (!proposed) return null;
  return {
    version: proposed,
    replaces: versions.find((v) => v.status === "in_use") ?? null,
    author: proposed.proposedBy ?? { login: "", name: "—" },
    at: proposed.proposedAt,
    reason: proposed.reason ?? "",
  };
}

function fromBackend(data: BackendExtractionOverview): ExtractionOverview {
  const versions = data.models.map(versionFromBackend);
  const inUse = versions.find((v) => v.version === data.version);
  return {
    inUse: data.version
      ? {
          version: data.version,
          model: data.llmModel ?? inUse?.llmModel ?? null,
          since: data.since,
          approvedBy: data.approvedBy ?? inUse?.decidedBy ?? null,
          verified: data.verifiedDescriptions,
          failed: data.failedDescriptions,
          corrected: data.correctedDescriptions,
        }
      : null,
    testReports: null,
    fields: data.fields.map((f) => ({ field: f.field, accuracy: f.f1, corrected: f.correctedShare })),
    proposal: proposalOf(versions),
    versions,
  };
}

const KOWALSKA = { login: "j.kowalska", name: "J. Kowalska" };
const NOWAK = { login: "a.nowak", name: "A. Nowak" };

function me(): Person {
  try {
    const user = JSON.parse(sessionStorage.getItem("maria.user") ?? "") as Person;
    if (user.login) return { login: user.login, name: user.name };
  } catch {
    // the dev user below
  }
  return { login: "dev", name: "Dev" };
}

const today = () => new Date().toISOString().slice(0, 10);

const FIELDS_NOW = { side: 0.96, birads: 0.58, clock: 0.79, size: 0.88, shape: 0.71, margin: 0.67, echo: 0.75 };
const CORRECTED = { side: 0.02, birads: 0.22, clock: 0.09, size: 0.12, shape: 0.14, margin: 0.27, echo: 0.11 };

// ?mock=proposal (a researcher's proposal waits), ?mock=mine (your own), ?mock=empty (nothing computed yet)
interface MockState {
  overview: ExtractionOverview;
  // the examples of each version, by the ids of the mock examples below
  sets: Record<string, string[]>;
}
let mockState: MockState | null = null;

function mockVersion(v: Partial<ExtractionVersion> & Pick<ExtractionVersion, "version" | "status">): ExtractionVersion {
  return {
    periods: [],
    f1: null,
    llmModel: "bielik-4.5b-v3.0-instruct",
    promptVersion: "v6",
    structuredOutput: true,
    examples: 1,
    editable: v.status === "new",
    proposedBy: null,
    proposedAt: null,
    decidedBy: null,
    reason: null,
    restore: false,
    ...v,
  };
}

function mockOverview(): MockState {
  const scenario = mockScenario();
  const proposed = scenario === "proposal" || scenario === "mine";
  const empty = scenario === "empty";
  const author = scenario === "mine" ? me() : KOWALSKA;
  const versions = empty
    ? [mockVersion({ version: "1", status: "in_use", periods: [{ from: "2026-10-06", to: null }] })]
    : [
        mockVersion({
          version: "3",
          status: proposed ? "proposed" : "new",
          examples: 3,
          f1: 0.88,
          proposedBy: proposed ? author : null,
          proposedAt: proposed ? "2026-11-10" : null,
          reason: proposed ? "Model pomijał BI-RADS zmiany, gdy był tylko we wniosku." : null,
        }),
        mockVersion({ version: "2", status: "in_use", periods: [{ from: "2026-10-06", to: null }], f1: 0.86, proposedBy: KOWALSKA, decidedBy: NOWAK }),
        mockVersion({ version: "1", status: "retired", llmModel: "bielik-4.5b-q4_k_m", periods: [{ from: "2026-09-01", to: "2026-10-06" }], f1: 0.81, proposedBy: NOWAK, decidedBy: NOWAK }),
      ];
  return {
    overview: {
      inUse: {
        version: empty ? "1" : "2",
        model: "bielik-4.5b-v3.0-instruct",
        since: "2026-10-06",
        approvedBy: NOWAK,
        verified: empty ? null : 146,
        failed: empty ? null : 3,
        corrected: empty ? null : 41,
      },
      testReports: empty ? null : 12,
      fields: Object.entries(FIELDS_NOW).map(([field, accuracy]) => ({
        field,
        accuracy: empty ? null : accuracy,
        corrected: empty ? null : CORRECTED[field as keyof typeof CORRECTED],
      })),
      proposal: proposalOf(versions),
      versions,
    },
    sets: empty ? { "1": ["01"] } : { "1": ["03"], "2": ["01"], "3": ["01", "02", "03"] },
  };
}

function mock(): MockState {
  mockState ??= mockOverview();
  return mockState;
}

export async function fetchExtraction(): Promise<ExtractionOverview> {
  if (MOCK_API) return mockDelay(structuredClone(mock().overview));
  const { data } = await request(api.get<BackendExtractionOverview>("/api/models/extraction/"));
  return fromBackend(data);
}

// made-up reports, short and without patient data
function observation(o: Partial<WireObservation> & Pick<WireObservation, "cytat">): WireObservation {
  return {
    modalnosc: "usg",
    lokalizacje: [],
    godzina: null,
    odleglosc_od_brodawki: null,
    typ: null,
    wymiary: null,
    glebokosc: null,
    ksztalt: null,
    brzeg: null,
    echogenicznosc: null,
    jednorodnosc: null,
    naciek_skory: null,
    ...o,
  };
}

function output(lesions: { strona: WireSide; birads: WireBiRads | null; obs: WireObservation }[], birads: WireBiRads, tekst: string): Extraction {
  const breast = { budowa: null, obrzek: null, zwapnienia: null, mikrozwapnienia: null, zmiany_ogniskowe: null, skora: { stan: null, naciek: null } };
  const zmiany: WireLesion[] = lesions.map((l, i) => ({ id: i + 1, strona: l.strona, birads: l.birads, obserwacje: [l.obs], polaczenie_obserwacji: null }));
  return { modalnosci: ["usg"], piersi: { lewa: breast, prawa: breast }, zmiany, wezly: [], wniosek: { birads, tekst, zalecenie: null } };
}

const examples = (): Record<string, Omit<FewShotExample, "isNew">> => ({
  "01": {
    id: "01",
    title: "USG, jedna zmiana",
    report: "USG piersi.\nPierś lewa: na godz. 2 ognisko hipoechogeniczne owalne, obwiedzione, wym. 8 x 6 mm.\nPierś prawa bez zmian ogniskowych.\n\nWnioski: BI-RADS 3, kontrola za 6 miesięcy.",
    output: output(
      [
        {
          strona: "lewa",
          birads: null,
          obs: observation({
            godzina: "2",
            typ: "ognisko",
            wymiary: { wartosci: [8, 6], jednostka: "mm", kwalifikator: "dokładny" },
            ksztalt: "owalny",
            brzeg: "obwiedziony",
            echogenicznosc: "hipoechogeniczna",
            cytat: "ognisko hipoechogeniczne owalne, obwiedzione, wym. 8 x 6 mm",
          }),
        },
      ],
      "3",
      "BI-RADS 3, kontrola za 6 miesięcy.",
    ),
  },
  "02": {
    id: "02",
    title: "USG, dwie zmiany",
    report: "USG piersi.\nPierś prawa: na godz. 11 ognisko hipoechogeniczne owalne, o granicach nieostrych, wym. 16 x 16 mm.\nPierś lewa: torbiel prosta 5 mm na godz. 3.\n\nWnioski: zmiana w piersi prawej BI-RADS 4A, wskazana biopsja.",
    output: output(
      [
        {
          strona: "prawa",
          birads: "4a",
          obs: observation({
            godzina: "11",
            typ: "ognisko",
            wymiary: { wartosci: [16, 16], jednostka: "mm", kwalifikator: "dokładny" },
            ksztalt: "owalny",
            brzeg: "nieostry",
            echogenicznosc: "hipoechogeniczna",
            cytat: "ognisko hipoechogeniczne owalne, o granicach nieostrych, wym. 16 x 16 mm",
          }),
        },
        {
          strona: "lewa",
          birads: null,
          obs: observation({
            godzina: "3",
            typ: "torbiel prosta",
            wymiary: { wartosci: [5], jednostka: "mm", kwalifikator: "dokładny" },
            echogenicznosc: "bezechowa",
            cytat: "torbiel prosta 5 mm na godz. 3",
          }),
        },
      ],
      "4a",
      "zmiana w piersi prawej BI-RADS 4A, wskazana biopsja.",
    ),
  },
  "03": {
    id: "03",
    title: "USG, BI-RADS we wniosku",
    report: "USG piersi.\nPierś prawa: na godz. 7 ognisko hipoechogeniczne nieregularne, o zatartych brzegach, wym. ok. 12 mm.\n\nWnioski: zmiana w piersi prawej BI-RADS 4B.",
    output: output(
      [
        {
          strona: "prawa",
          birads: "4b",
          obs: observation({
            godzina: "7",
            typ: "ognisko",
            wymiary: { wartosci: [12], jednostka: "mm", kwalifikator: "około" },
            ksztalt: "nieregularny",
            brzeg: "zatarty",
            echogenicznosc: "hipoechogeniczna",
            cytat: "ognisko hipoechogeniczne nieregularne, o zatartych brzegach, wym. ok. 12 mm",
          }),
        },
      ],
      "4b",
      "zmiana w piersi prawej BI-RADS 4B.",
    ),
  },
});

function mockConfig(version: string): VersionConfig {
  const state = mock();
  const v = state.overview.versions.find((item) => item.version === version);
  const all = examples();
  return {
    version,
    name: "extraction",
    status: Object.entries(STATUS).find(([, mapped]) => mapped === v?.status)?.[0] ?? "new",
    llmModel: v?.llmModel ?? "",
    promptVersion: v?.promptVersion ?? "",
    structuredOutput: v?.structuredOutput ?? true,
    fewShotExamples: (state.sets[version] ?? []).map((id) => ({ report: all[id].report, output: all[id].output })),
    editable: v?.editable ?? false,
  };
}

export async function fetchFewShot(version: string): Promise<FewShotExample[]> {
  if (MOCK_API) {
    const state = mock();
    const inUse = state.sets[state.overview.inUse?.version ?? ""] ?? [];
    const all = examples();
    return mockDelay((state.sets[version] ?? []).map((id) => ({ ...all[id], isNew: !inUse.includes(id) })));
  }
  const { data } = await request(api.get<FewShotExample[]>(`/api/models/extraction/few-shot/${encodeURIComponent(version)}/`));
  return data;
}

export async function fetchVersion(version: string): Promise<VersionConfig> {
  if (MOCK_API) return mockDelay(mockConfig(version));
  const { data } = await request(api.get<VersionConfig>(versionPath(version)));
  return data;
}

// the models the LLM server offers; empty when the server can't be asked
export async function fetchLlmModels(): Promise<string[]> {
  if (MOCK_API) return mockDelay(["bielik-4.5b-v3.0-instruct", "bielik-11b-v2.6-instruct"]);
  const { data } = await request(api.get<string[]>("/api/models/extraction/llm-models/"));
  return data;
}

const versionPath = (version: string, action?: string) =>
  `/api/models/extraction/versions/${encodeURIComponent(version)}/${action ? `${action}/` : ""}`;

// a new draft with the configuration of the version in use
export async function createVersion(): Promise<string> {
  if (MOCK_API) {
    const state = mock();
    const base = state.overview.versions.find((v) => v.status === "in_use");
    const next = String(Math.max(0, ...state.overview.versions.map((v) => Number(v.version) || 0)) + 1);
    state.overview.versions.unshift(
      mockVersion({ version: next, status: "new", llmModel: base?.llmModel ?? "", structuredOutput: base?.structuredOutput ?? true, examples: base?.examples ?? 0 }),
    );
    state.sets[next] = [...(state.sets[base?.version ?? ""] ?? [])];
    record("version_created", `ext ${next}`, base ? `z wersji ${base.version}` : null);
    return mockDelay(next, 300);
  }
  const { data } = await request(api.post<VersionConfig>("/api/models/extraction/versions/"));
  return data.version;
}

export async function updateDraft(version: string, changes: DraftChanges): Promise<VersionConfig> {
  if (MOCK_API) {
    const state = mock();
    const v = state.overview.versions.find((item) => item.version === version);
    if (v) {
      if (changes.llm_model !== undefined) v.llmModel = changes.llm_model;
      if (changes.structured_output !== undefined) v.structuredOutput = changes.structured_output;
      if (changes.few_shot_examples !== undefined) {
        const all = examples();
        state.sets[version] = changes.few_shot_examples.map((e) => Object.keys(all).find((id) => all[id].report === e.report)).filter((id): id is string => !!id);
        v.examples = state.sets[version].length;
      }
    }
    record("version_changed", `ext ${version}`, Object.keys(changes).join(", "));
    return mockDelay(mockConfig(version), 300);
  }
  const { data } = await request(api.patch<VersionConfig>(versionPath(version), changes));
  return data;
}

// a verified report (its text and accepted form) as a new example of the draft
export async function addExample(version: string, reportId: number): Promise<VersionConfig> {
  if (MOCK_API) return mockDelay(mockConfig(version), 300);
  const { data } = await request(api.post<VersionConfig>(versionPath(version, "examples"), { report_id: reportId }));
  return data;
}

// mock decisions update the mock state
function decide(version: string, change: (v: ExtractionVersion, state: MockState) => void) {
  const state = mock();
  const v = state.overview.versions.find((item) => item.version === version);
  if (v) change(v, state);
  state.overview.proposal = proposalOf(state.overview.versions);
}

export async function proposeExtraction(version: string, reason: string): Promise<string> {
  if (MOCK_API) {
    decide(version, (v) => Object.assign(v, { restore: v.status === "retired", status: "proposed", editable: false, proposedBy: me(), proposedAt: today(), reason }));
    record("model_proposed", `ext ${version}`, reason);
    return mockDelay(version, 400);
  }
  await request(api.post(versionPath(version, "propose"), { reason }));
  return version;
}

export async function withdrawExtraction(version: string): Promise<string> {
  if (MOCK_API) {
    decide(version, (v) => Object.assign(v, { status: v.restore ? "retired" : "new", editable: !v.restore, restore: false, proposedBy: null, proposedAt: null, reason: null }));
    record("proposal_withdrawn", `ext ${version}`);
    return mockDelay(version);
  }
  await request(api.post(versionPath(version, "withdraw")));
  return version;
}

// an admin puts the proposal in use
export async function applyExtraction(version: string): Promise<string> {
  if (MOCK_API) {
    decide(version, (v, state) => {
      const since = today();
      for (const other of state.overview.versions) {
        if (other.status === "in_use") Object.assign(other, { status: "retired", periods: other.periods.map((p) => (p.to ? p : { ...p, to: since })) });
      }
      Object.assign(v, { status: "in_use", restore: false, decidedBy: me(), periods: [...v.periods, { from: since, to: null }] });
      if (state.overview.inUse) Object.assign(state.overview.inUse, { version, model: v.llmModel, since, approvedBy: me() });
    });
    record("model_promoted", `ext ${version}`);
    return mockDelay(version);
  }
  await request(api.post(versionPath(version, "promote")));
  return version;
}

export async function rejectExtraction(version: string, reason: string): Promise<string> {
  if (MOCK_API) {
    decide(version, (v) => Object.assign(v, { status: v.restore ? "retired" : "rejected", restore: false, decidedBy: me(), reason }));
    record("model_rejected", `ext ${version}`, reason);
    return mockDelay(version);
  }
  await request(api.post(versionPath(version, "reject"), { reason }));
  return version;
}
