import axios from "axios";

import { t } from "./i18n";

// empty: same origin as the app, through the gateway; plain `npm run dev` sets VITE_API_URL
export const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export const api = axios.create({
  baseURL: API_URL,
  timeout: 15000,
  withCredentials: true,
  xsrfCookieName: "csrftoken",
  xsrfHeaderName: "X-CSRFToken",
  withXSRFToken: true,
});

// the server no longer knows the session (it expired or was signed out elsewhere)
const sessionEnded = new Set<() => void>();

export function onSessionEnd(listener: () => void): () => void {
  sessionEnded.add(listener);
  return () => sessionEnded.delete(listener);
}

let checking: Promise<boolean> | null = null;

// a refusal can also mean a missing permission; the profile tells whether there is a session at all
export function hasSession(): Promise<boolean> {
  checking ??= api
    .get("/api/profile/", { validateStatus: () => true })
    .then((response) => response.status !== 401 && response.status !== 403)
    .catch(() => true)
    .finally(() => (checking = null));
  return checking;
}

// sign-in answers 401 for a wrong password, and the profile is the check itself
const NOT_CHECKED = /^\/api\/(auth\/|profile\/)/;

api.interceptors.response.use(undefined, async (error: unknown) => {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    if ((status === 401 || status === 403) && !NOT_CHECKED.test(error.config?.url ?? "") && !(await hasSession())) {
      sessionEnded.forEach((listener) => listener());
    }
  }
  return Promise.reject(error);
});


export type ApiErrorKind = "orthanc_unavailable" | "orthanc_unauthorized" | "backend_unreachable" | "unknown";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly kind: ApiErrorKind,
    // none when the server didn't answer
    readonly status?: number,
  ) {
    super(message);
  }
}

export function handleApiError(error: unknown, fallbackUrl?: string): never {
  if (error instanceof ApiError) {
    throw error;
  }
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as { code?: string; detail?: string } | undefined;
    const status = error.response?.status;

    if (body?.code === "orthanc_unavailable") {
      throw new ApiError(t("api.orthancUnavailable"), "orthanc_unavailable", status);
    }
    if (body?.code === "orthanc_unauthorized") {
      throw new ApiError(t("api.orthancUnauthorized"), "orthanc_unauthorized", status);
    }
    if (body?.detail) {
      throw new ApiError(body.detail, body.code === "backend_unreachable" ? "backend_unreachable" : "unknown", status);
    }
    if (!error.response) {
      throw new ApiError(t("api.unreachable", { url: fallbackUrl || API_URL || window.location.origin }), "backend_unreachable");
    }
    // the router's own 404 page, not an answer from a view: the endpoint isn't there yet
    if (status === 404 && typeof error.response.data !== "object") {
      throw new ApiError(t("api.notAvailable"), "unknown", status);
    }
    throw new ApiError(t("api.http", { status: error.response.status }), "unknown", status);
  }

  throw new ApiError(t("api.unknown"), "unknown");
}

// a request whose errors always come out as ApiError
export async function request<T>(sent: Promise<T>, fallbackUrl?: string): Promise<T> {
  try {
    return await sent;
  } catch (error) {
    handleApiError(error, fallbackUrl);
  }
}

// no answer or a server fault may pass on a second try; a refusal with a reason won't
export const canRetry = (error: unknown) => !(error instanceof ApiError) || error.status === undefined || error.status >= 500;

// text for an error box: our own messages as they are, anything else (axios, mocks) gets a generic one
export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (axios.isAxiosError(error)) return error.response ? t("api.http", { status: error.response.status }) : t("api.unreachable", { url: API_URL || window.location.origin });
  return t("api.unknown");
}

export type PacsStatus = "ok" | "unauthorized" | "unreachable" | "unknown";

export async function fetchPacsStatus(): Promise<PacsStatus> {
  try {
    const { data } = await api.get<{ orthanc?: PacsStatus }>("/api/health", { validateStatus: () => true });
    return data?.orthanc ?? "unknown";
  } catch {
    return "unknown";
  }
}
