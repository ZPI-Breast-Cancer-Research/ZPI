import { api } from "../api";
import { mockDelay, mockScenario, MOCK_API } from "../mock";
import type { Extraction, WireBiRads, WireLesion, WireObservation, WireSide } from "../review/extraction";
import { record } from "../settings/audit";
import type { GateCheck, Person, Proposal, VersionStatus } from "./api";

// the language model and the few-shot examples change apart
export type ExtractionPart = "model" | "few_shot";

export interface ExtractionVersion {
  // a model's name or a few-shot version
  name: string;
  status: VersionStatus;
  periods: { from: string; to: string | null }[];
  // lesions found on the test set (F1), with the other part as it is in use
  f1: number | null;
  // few-shot only
  examples: number | null;
  proposedBy: Person | null;
  decidedBy: Person | null;
  reason: string | null;
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
  part: ExtractionPart;
  name: string;
  replaces: string;
  author: Proposal["author"];
  at: string;
  reason: string;
  gate: GateCheck[] | null;
  fields: { field: string; current: number | null; next: number | null }[] | null;
  f1: { current: number | null; next: number | null } | null;
}

export interface ExtractionOverview {
  inUse: {
    model: string | null;
    fewShot: string | null;
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
  models: ExtractionVersion[];
  fewShots: ExtractionVersion[];
}

export interface FewShotExample {
  id: string;
  title: string;
  report: string;
  output: Extraction;
  // not in the set in use
  isNew: boolean;
}

function isExtractionOverview(data: unknown): data is ExtractionOverview {
  return !!data && typeof data === "object" && "fewShots" in data && Array.isArray((data as ExtractionOverview).models);
}

// the shape the backend sends today, read into the new one
interface OldExtraction {
  version: string | null;
  since: string | null;
  examplePool: number;
  fields: { field: string; f1: number | null; correctedShare: number | null }[];
}

function fromOld(old: OldExtraction): ExtractionOverview {
  return {
    inUse: old.version
      ? { model: old.version, fewShot: null, since: old.since, approvedBy: null, verified: old.examplePool, failed: null, corrected: null }
      : null,
    testReports: null,
    fields: old.fields.map((f) => ({ field: f.field, accuracy: f.f1, corrected: f.correctedShare })),
    proposal: null,
    models: [],
    fewShots: [],
  };
}

const KOWALSKA = { login: "j.kowalska", name: "J. Kowalska" };
const NOWAK = { login: "a.nowak", name: "A. Nowak" };

function me(): Proposal["author"] {
  try {
    const user = JSON.parse(sessionStorage.getItem("maria.user") ?? "") as Person & { role: string };
    if (user.login) return { login: user.login, name: user.name, role: user.role === "admin" ? "admin" : "researcher" };
  } catch {
    // the dev user below
  }
  return { login: "dev", name: "Dev", role: import.meta.env.VITE_SKIP_LOGIN === "admin" ? "admin" : "researcher" };
}

const today = () => new Date().toISOString().slice(0, 10);

const FIELDS_NOW = { side: 0.96, birads: 0.58, clock: 0.79, size: 0.88, shape: 0.71, margin: 0.67, echo: 0.75 };
const FIELDS_V7 = { side: 0.96, birads: 0.83, clock: 0.79, size: 0.92, shape: 0.71, margin: 0.65, echo: 0.75 };
const CORRECTED = { side: 0.02, birads: 0.22, location: 0.09, size: 0.12, shape: 0.14, margin: 0.27, echo: 0.11 };

function fewShotProposal(author: Proposal["author"]): ExtractionProposal {
  return {
    part: "few_shot",
    name: "v7",
    replaces: "v6",
    author,
    at: "2026-11-10",
    reason: "Model pomijał BI-RADS zmiany, gdy był tylko we wniosku.",
    gate: [
      { rule: "no_field_drop", threshold: 5, value: 2, baseline: null, studyNumber: null, field: "margin", passed: true },
      { rule: "failed_not_more", threshold: null, value: 0, baseline: 0, studyNumber: null, passed: true },
    ],
    fields: Object.entries(FIELDS_NOW).map(([field, current]) => ({ field, current, next: FIELDS_V7[field as keyof typeof FIELDS_V7] })),
    f1: { current: 0.86, next: 0.88 },
  };
}

// ?mock=proposal (a researcher's few-shot proposal waits), ?mock=mine (your own), ?mock=empty (nothing computed yet)
let mockState: ExtractionOverview | null = null;

function mockOverview(): ExtractionOverview {
  const scenario = mockScenario();
  const proposed = scenario === "proposal" || scenario === "mine";
  const empty = scenario === "empty";
  const version = (v: Partial<ExtractionVersion> & Pick<ExtractionVersion, "name" | "status">): ExtractionVersion => ({
    periods: [],
    f1: null,
    examples: null,
    proposedBy: null,
    decidedBy: null,
    reason: null,
    ...v,
  });
  return {
    inUse: {
      model: "Bielik 4.5B q8_0",
      fewShot: "v6",
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
    proposal: proposed ? fewShotProposal(scenario === "mine" ? me() : { ...KOWALSKA, role: "researcher" }) : null,
    models: empty
      ? [version({ name: "Bielik 4.5B q8_0", status: "in_use", periods: [{ from: "2026-10-06", to: null }] })]
      : [
          version({ name: "Bielik 11B q4_k_m", status: "new", f1: 0.9 }),
          version({ name: "Bielik 4.5B q8_0", status: "in_use", periods: [{ from: "2026-10-06", to: null }], f1: 0.86, proposedBy: KOWALSKA, decidedBy: NOWAK }),
          version({ name: "Bielik 4.5B q4_k_m", status: "retired", periods: [{ from: "2026-09-01", to: "2026-10-06" }], f1: 0.81, proposedBy: NOWAK, decidedBy: NOWAK }),
        ],
    fewShots: empty
      ? [version({ name: "v6", status: "in_use", examples: 1, periods: [{ from: "2026-10-06", to: null }] })]
      : [
          version({ name: "v7", status: proposed ? "proposed" : "new", examples: 3, f1: 0.88, proposedBy: proposed ? KOWALSKA : null }),
          version({ name: "v6", status: "in_use", examples: 1, periods: [{ from: "2026-10-06", to: null }], f1: 0.86, proposedBy: KOWALSKA, decidedBy: NOWAK }),
          version({ name: "v5", status: "retired", examples: 1, periods: [{ from: "2026-09-01", to: "2026-10-06" }], f1: 0.84, proposedBy: NOWAK, decidedBy: NOWAK }),
        ],
  };
}

export async function fetchExtraction(): Promise<ExtractionOverview> {
  if (MOCK_API) {
    mockState ??= mockOverview();
    return mockDelay(structuredClone(mockState));
  }
  const { data } = await api.get<ExtractionOverview | OldExtraction>("/api/models/extraction/");
  return isExtractionOverview(data) ? data : fromOld(data);
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

const EXAMPLES: Record<string, Omit<FewShotExample, "isNew">> = {
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
};

const SETS: Record<string, string[]> = { v5: ["03"], v6: ["01"], v7: ["01", "02", "03"] };

export async function fetchFewShot(version: string): Promise<FewShotExample[]> {
  if (MOCK_API) {
    const inUse = SETS[mockState?.inUse?.fewShot ?? "v6"] ?? [];
    return mockDelay((SETS[version] ?? []).map((id) => ({ ...EXAMPLES[id], isNew: !inUse.includes(id) })));
  }
  const { data } = await api.get<FewShotExample[]>(`/api/models/extraction/few-shot/${encodeURIComponent(version)}/`);
  return data;
}

export async function fetchExtractionGate(part: ExtractionPart, name: string): Promise<GateCheck[] | null> {
  if (MOCK_API) return mockDelay(part === "few_shot" && name === "v7" ? fewShotProposal(me()).gate : null);
  const { data } = await api.get<GateCheck[] | null>(`/api/models/extraction/${part}/${encodeURIComponent(name)}/gate/`);
  return data;
}

// mock decisions update the mock state
function updateMock(change: (state: ExtractionOverview) => void) {
  mockState ??= mockOverview();
  change(mockState);
}

const listOf = (state: ExtractionOverview, part: ExtractionPart) => (part === "model" ? state.models : state.fewShots);

function putInUse(state: ExtractionOverview, part: ExtractionPart, name: string, reason: string | null) {
  const since = today();
  const { login, name: who } = me();
  for (const v of listOf(state, part)) {
    if (v.status === "in_use") Object.assign(v, { status: "retired", periods: v.periods.map((p) => (p.to ? p : { ...p, to: since })) });
    if (v.name === name) {
      Object.assign(v, { status: "in_use", periods: [...v.periods, { from: since, to: null }], decidedBy: { login, name: who } });
      v.reason = state.proposal?.reason ?? reason;
      if (!state.proposal) v.proposedBy = { login, name: who };
    }
  }
  if (state.inUse) Object.assign(state.inUse, part === "model" ? { model: name } : { fewShot: name }, { since, approvedBy: { login, name: who } });
  state.proposal = null;
}

const path = (part: ExtractionPart, name: string, action: string) => `/api/models/extraction/${part}/${encodeURIComponent(name)}/${action}/`;

export async function proposeExtraction(part: ExtractionPart, name: string, reason: string): Promise<string> {
  if (MOCK_API) {
    updateMock((state) => {
      const v = listOf(state, part).find((item) => item.name === name);
      const current = part === "model" ? state.inUse?.model : state.inUse?.fewShot;
      if (!v || !current) return;
      const author = me();
      const restore = v.status === "retired";
      v.status = "proposed";
      if (!restore) Object.assign(v, { proposedBy: { login: author.login, name: author.name }, reason });
      const inUse = listOf(state, part).find((item) => item.status === "in_use");
      state.proposal = { part, name, replaces: current, author, at: today(), reason, gate: null, fields: null, f1: { current: inUse?.f1 ?? null, next: v.f1 } };
    });
    record("model_proposed", name, reason);
    return mockDelay(name, 400);
  }
  await api.post("/api/models/extraction/proposals/", { part, name, reason });
  record("model_proposed", name, reason);
  return name;
}

export async function withdrawExtraction(part: ExtractionPart, name: string): Promise<string> {
  if (MOCK_API) {
    updateMock((state) => {
      const v = listOf(state, part).find((item) => item.name === name);
      if (v) Object.assign(v, v.periods.length ? { status: "retired" } : { status: "new", proposedBy: null, reason: null });
      state.proposal = null;
    });
  } else {
    await api.post(path(part, name, "withdraw"));
  }
  record("proposal_withdrawn", name);
  return name;
}

// reason only for an admin's own change
export async function applyExtraction(part: ExtractionPart, name: string, reason: string | null = null): Promise<string> {
  if (MOCK_API) {
    updateMock((state) => putInUse(state, part, name, reason));
  } else {
    await api.post(path(part, name, "promote"), { reason });
  }
  record("model_promoted", name, reason);
  return name;
}

export async function rejectExtraction(part: ExtractionPart, name: string, reason: string): Promise<string> {
  if (MOCK_API) {
    updateMock((state) => {
      const v = listOf(state, part).find((item) => item.name === name);
      const { login, name: who } = me();
      if (v) Object.assign(v, { status: v.periods.length ? "retired" : "rejected", decidedBy: { login, name: who }, reason });
      state.proposal = null;
    });
  } else {
    await api.post(path(part, name, "reject"), { reason });
  }
  record("model_rejected", name, reason);
  return name;
}
