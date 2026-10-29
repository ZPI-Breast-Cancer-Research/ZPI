import { fetchStudies } from "./api";

// VITE_MOCK_API=true uses fake data even where a real endpoint exists
export const MOCK_API = import.meta.env.VITE_MOCK_API === "true";

export function mockDelay<T>(value: T, ms = 200): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

// lets you preview other states without a backend, e.g. /modele?mock=candidate
export function mockScenario(): string | null {
  return new URLSearchParams(window.location.search).get("mock");
}

// mock cases borrow a real MR study from Orthanc (if there is one) so the viewer has images to show
export async function mockStudyUid(index: number): Promise<string | null> {
  try {
    const studies = (await fetchStudies())
      .filter((s) => s.study_instance_uid && s.modalities.includes("MR"))
      .sort((a, b) => b.series_count - a.series_count);
    return studies.length ? studies[index % studies.length].study_instance_uid : null;
  } catch {
    return null;
  }
}
