

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
let mrStudies: Promise<string[]> | null = null;

export async function mockStudyUid(index: number): Promise<string | null> {
  // loaded lazily, the viewer code is heavy and most mocks don't need it
  mrStudies ??= import("./viewer/dicomweb").then((m) => m.listMrStudies()).catch(() => []);
  const studies = await mrStudies;
  return studies.length ? studies[index % studies.length] : null;
}
