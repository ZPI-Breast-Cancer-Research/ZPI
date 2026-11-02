import axios from "axios";

export const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export const api = axios.create({ baseURL: API_URL, timeout: 15000 });

export interface Study {
  orthanc_id: string;
  study_instance_uid: string | null;
  patient_id: string | null;
  study_date: string | null;
  description: string | null;
  modalities: string[];
  series_count: number;
  viewer_url: string | null;
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

export async function fetchStudies(): Promise<Study[]> {
  try {
    const { data } = await api.get<Study[]>("/api/studies");
    // plain `npm run dev` has no gateway, so /api returns index.html instead of JSON
    if (!Array.isArray(data)) {
      throw new ApiError(
        `The backend API at ${API_URL || window.location.origin} did not return a study list.`,
        "backend_unreachable",
      );
    }
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (axios.isAxiosError(error)) {
      const body = error.response?.data as { code?: string; detail?: string } | undefined;
      if (body?.code === "orthanc_unavailable") {
        throw new ApiError(body.detail ?? "Orthanc is unavailable.", "orthanc_unavailable");
      }
      if (body?.code === "orthanc_unauthorized") {
        throw new ApiError(body.detail ?? "Orthanc rejected the credentials.", "orthanc_unauthorized");
      }
      if (!error.response) {
        throw new ApiError(
          `Cannot reach the backend API at ${API_URL || window.location.origin}.`,
          "backend_unreachable",
        );
      }
      throw new ApiError(body?.detail ?? `Backend returned HTTP ${error.response.status}.`, "unknown");
    }
    throw new ApiError("Unexpected error while loading studies.", "unknown");
  }
}

export async function sendStudy(archiveFile?: File, reportFile?: File): Promise<any> {
  const formData = new FormData();
  if (archiveFile) {
    formData.append("archives", archiveFile);
  }
  if (reportFile) {
    formData.append("report", reportFile);
  }

  try {
    const { data } = await api.post("/api/studies/import/", formData);
    return data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const body = error.response?.data as { code?: string; detail?: string } | undefined;
      throw new ApiError(body?.detail || "Błąd podczas wysyłania badania.", "unknown");
    }
    throw new ApiError("Nieoczekiwany błąd podczas wysyłania.", "unknown");
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
