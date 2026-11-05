import { fetchPacsStatus } from "../api";
import { mockDelay, mockScenario } from "../mock";

export type Component = "orthanc" | "pacs" | "segmentation" | "extraction" | "training" | "llm" | "registry";
export type ComponentState = "ok" | "slow" | "down" | "unknown";

export interface ComponentStatus {
  key: Component;
  state: ComponentState;
  // when it stopped answering, for "nie odpowiada od 14 min"
  since: string | null;
  detail: string | null;
}

export interface SystemStatus {
  checkedAt: string;
  components: ComponentStatus[];
  profile: "cpu" | "gpu1" | "gpu2";
  retraining: boolean;
}

const minutesAgo = (n: number) => new Date(Date.now() - n * 60_000).toISOString();

// TODO: /api/health only knows Orthanc so far; the workers, LLM and MLflow are faked.
// ?mock=outage previews a stuck training worker and a slow LLM
export async function fetchSystemStatus(): Promise<SystemStatus> {
  const outage = mockScenario() === "outage";
  const orthanc = await fetchPacsStatus();
  const components: ComponentStatus[] = [
    {
      key: "orthanc",
      state: orthanc === "ok" ? "ok" : orthanc === "unknown" ? "unknown" : "down",
      since: null,
      detail: orthanc === "unauthorized" ? "401" : null,
    },
    { key: "pacs", state: "ok", since: null, detail: "AE MARIA → PACS_SZPITAL" },
    { key: "segmentation", state: "ok", since: null, detail: "2 w kolejce" },
    { key: "extraction", state: "ok", since: null, detail: null },
    { key: "training", state: outage ? "down" : "ok", since: outage ? minutesAgo(14) : null, detail: null },
    { key: "llm", state: outage ? "slow" : "ok", since: null, detail: outage ? "~9 s na opis" : null },
    { key: "registry", state: "ok", since: null, detail: "MLflow" },
  ];
  return mockDelay({ checkedAt: new Date().toISOString(), components, profile: "gpu1", retraining: true }, 300);
}
