// VITE_MOCK_API=true uses fake data even where a real endpoint exists
export const MOCK_API = import.meta.env.VITE_MOCK_API === "true";

export function mockDelay<T>(value: T, ms = 200): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

// lets you preview other states without a backend, e.g. /modele?mock=candidate
export function mockScenario(): string | null {
  return new URLSearchParams(window.location.search).get("mock");
}
