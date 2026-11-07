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


export class ApiError extends Error {
  constructor(
    message: string,
    readonly kind: "orthanc_unavailable" | "orthanc_unauthorized" | "backend_unreachable" | "unknown",
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

    if (body?.code === "orthanc_unavailable") {
      throw new ApiError(t("api.orthancUnavailable"), "orthanc_unavailable");
    }
    if (body?.code === "orthanc_unauthorized") {
      throw new ApiError(t("api.orthancUnauthorized"), "orthanc_unauthorized");
    }
    if (body?.detail) {
      const kind = (["orthanc_unavailable", "orthanc_unauthorized", "backend_unreachable"].includes(body.code || "") 
        ? body.code 
        : "unknown") as "orthanc_unavailable" | "orthanc_unauthorized" | "backend_unreachable" | "unknown";
        
      throw new ApiError(body.detail, kind);
    }
    if (!error.response) {
      throw new ApiError(t("api.unreachable", { url: fallbackUrl || "backend" }), "backend_unreachable");
    }
    throw new ApiError(t("api.http", { status: error.response.status }), "unknown");
  }

  throw new ApiError(t("api.unknown"), "unknown");
}

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
