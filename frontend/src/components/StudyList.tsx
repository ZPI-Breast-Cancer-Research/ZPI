import { useQuery } from "@tanstack/react-query";

import { ApiError, fetchStudies, type Study } from "../api";
import { t } from "../i18n";

function formatDicomDate(value: string | null): string {
  if (!value || !/^\d{8}$/.test(value)) return value ?? "—";
  return `${value.slice(6, 8)}.${value.slice(4, 6)}.${value.slice(0, 4)}`;
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
    return <p className="state">{t("studies.loading")}</p>;
  }

  if (error) {
    const kind = error instanceof ApiError ? error.kind : "unknown";
    const title =
      kind === "orthanc_unavailable"
        ? t("studies.error.orthancUnavailable")
        : kind === "orthanc_unauthorized"
          ? t("studies.error.orthancUnauthorized")
          : t("studies.error.title");
    return (
      <div className="state state--error" role="alert">
        <h3>{title}</h3>
        <p>{error.message}</p>
        <button className="btn" onClick={() => refetch()} disabled={isFetching}>
          {isFetching ? t("studies.retrying") : t("studies.retry")}
        </button>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="state">
        <h3>{t("studies.empty.title")}</h3>
        <p>{t("studies.empty.body")}</p>
      </div>
    );
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>{t("studies.col.patient")}</th>
          <th>{t("studies.col.date")}</th>
          <th>{t("studies.col.description")}</th>
          <th>{t("studies.col.modalities")}</th>
          <th className="cell-right">{t("studies.col.series")}</th>
        </tr>
      </thead>
      <tbody>
        {data.map((study) => (
          <tr
            key={study.orthanc_id}
            className={study.viewer_url ? "is-clickable" : undefined}
            tabIndex={study.viewer_url ? 0 : undefined}
            title={study.viewer_url ? t("studies.openViewer") : t("studies.noViewer")}
            onClick={() => openViewer(study)}
            onKeyDown={(event) => event.key === "Enter" && openViewer(study)}
          >
            <td className="cell-strong">{study.patient_id ?? "—"}</td>
            <td>{formatDicomDate(study.study_date)}</td>
            <td>{study.description || "—"}</td>
            <td>{study.modalities.join(", ") || "—"}</td>
            <td className="cell-right">{study.series_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
