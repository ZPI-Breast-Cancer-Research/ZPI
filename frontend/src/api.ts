import axios from "axios";

import { t } from "./i18n";

// empty: same origin as the app, through the gateway; plain `npm run dev` sets VITE_API_URL
export const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export const api = axios.create({ baseURL: API_URL, timeout: 15000 });

export interface Study {
  orthanc_id: string;
  study_instance_uid: string | null;
  patient_id: string | null;
  study_date: string | null;
  description: string | null;
  modalities: string[];
  series_count: number;
  extraction_status: string;
  segmentation_status: string;
  uncertainty: number | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly kind: "orthanc_unavailable" | "orthanc_unauthorized" | "backend_unreachable" | "unknown",
  ) {
    super(message);
  }
}

// the backend's `detail` is in English and meant for developers, so the UI says it in its own words
export async function fetchStudies(): Promise<Study[]> {
  const url = API_URL || window.location.origin;
  try {
    const { data } = await api.get<Study[]>("/api/studies");
    // plain `npm run dev` has no gateway, so /api returns index.html instead of JSON
    if (!Array.isArray(data)) throw new ApiError(t("api.badResponse", { url }), "backend_unreachable");
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (axios.isAxiosError(error)) {
      const body = error.response?.data as { code?: string } | undefined;
      if (body?.code === "orthanc_unavailable") throw new ApiError(t("api.orthancUnavailable"), "orthanc_unavailable");
      if (body?.code === "orthanc_unauthorized") throw new ApiError(t("api.orthancUnauthorized"), "orthanc_unauthorized");
      if (!error.response) throw new ApiError(t("api.unreachable", { url }), "backend_unreachable");
      throw new ApiError(t("api.http", { status: error.response.status }), "unknown");
    }
    throw new ApiError(t("api.unknown"), "unknown");
  }
}

// text for an error box: our own messages as they are, anything else (axios, mocks) gets a generic one
export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (axios.isAxiosError(error)) return error.response ? t("api.http", { status: error.response.status }) : t("api.unreachable", { url: API_URL || window.location.origin });
  return t("api.unknown");
}

export async function sendStudy(archiveFile?: File, reportFile?: File): Promise<unknown> {
  const formData = new FormData();
  if (archiveFile) formData.append("archives", archiveFile);
  if (reportFile) formData.append("report", reportFile);

  try {
    const { data } = await api.post("/api/studies/import/", formData);
    return data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const body = error.response?.data as { code?: string; detail?: string } | undefined;
      throw new ApiError(body?.detail || t("api.sendFailed"), "unknown");
    }
    throw new ApiError(t("api.unknown"), "unknown");
  }
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
