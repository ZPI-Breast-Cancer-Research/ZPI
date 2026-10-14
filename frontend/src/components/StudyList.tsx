import { useQuery } from "@tanstack/react-query";

import { ApiError, fetchStudies, type Study } from "../api";

function formatDicomDate(value: string | null): string {
  if (!value || !/^\d{8}$/.test(value)) return value ?? "—";
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

function openViewer(study: Study) {
  if (study.viewer_url) window.open(study.viewer_url, "_blank", "noopener,noreferrer");
}

export default function StudyList() {
  const { data, error, isPending, isFetching, refetch } = useQuery({
    queryKey: ["studies"],
    queryFn: fetchStudies,
    retry: false,
  });

  if (isPending) {
    return <p className="state">Loading studies…</p>;
  }

  if (error) {
    const kind = error instanceof ApiError ? error.kind : "unknown";
    const title =
      kind === "orthanc_unavailable"
        ? "DICOM server (Orthanc) is unavailable"
        : kind === "orthanc_unauthorized"
          ? "DICOM server (Orthanc) rejected the backend's credentials"
          : "Could not load studies";
    return (
      <div className="state state--error" role="alert">
        <strong>{title}</strong>
        <p>{error.message}</p>
        <button onClick={() => refetch()} disabled={isFetching}>
          {isFetching ? "Retrying…" : "Retry"}
        </button>
      </div>
    );
  }

  if (data.length === 0) {
    return <p className="state">No studies found in Orthanc yet.</p>;
  }

  return (
    <table className="studies">
      <thead>
        <tr>
          <th>Patient ID</th>
          <th>Date</th>
          <th>Description</th>
          <th>Modalities</th>
          <th>Series</th>
        </tr>
      </thead>
      <tbody>
        {data.map((study) => (
          <tr
            key={study.orthanc_id}
            className={study.viewer_url ? "clickable" : undefined}
            tabIndex={study.viewer_url ? 0 : undefined}
            title={study.viewer_url ? "Open in viewer" : "No StudyInstanceUID – viewer unavailable"}
            onClick={() => openViewer(study)}
            onKeyDown={(event) => event.key === "Enter" && openViewer(study)}
          >
            <td>{study.patient_id ?? "—"}</td>
            <td>{formatDicomDate(study.study_date)}</td>
            <td>{study.description || "—"}</td>
            <td>{study.modalities.join(", ") || "—"}</td>
            <td>{study.series_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
