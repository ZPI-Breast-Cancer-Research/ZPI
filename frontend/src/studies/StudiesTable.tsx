import { useState } from "react";
import { Link } from "react-router-dom";

import WarningIcon from "../components/WarningIcon";
import { formatDate, formatDecimal } from "../format";
import { t, type MessageKey } from "../i18n";
import type { ImageStatus, ReportStatus, StudyRow } from "./api";

export type Filter = "all" | "processing" | "to_review" | "verified" | "no_report";

const FILTERS: { key: Filter; label: MessageKey }[] = [
  { key: "all", label: "studies.all" },
  { key: "processing", label: "studies.processing" },
  { key: "to_review", label: "studies.toReview" },
  { key: "verified", label: "studies.verified" },
  { key: "no_report", label: "studies.noReport" },
];

const IMAGE_CLASS: Record<ImageStatus, string> = {
  queued: "status",
  processing: "status status--running",
  error: "status status--warning",
  to_review: "status",
  saving: "status status--running",
  verified_unchanged: "status status--confirmed",
  verified_corrected: "status status--corrected",
};

const REPORT_CLASS: Record<ReportStatus, string> = {
  missing: "status",
  extracting: "status status--running",
  ready: "status",
  to_review: "status",
  verified: "status status--confirmed",
};

export function parseFilter(value: string | null): Filter {
  return FILTERS.find((f) => f.key === value)?.key ?? "all";
}

function matches(row: StudyRow, filter: Filter, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (q && !`${row.number ?? ""} ${row.patientId}`.toLowerCase().includes(q)) return false;
  switch (filter) {
    case "all":
      return true;
    case "processing":
      return row.image === "queued" || row.image === "processing" || row.image === "saving";
    case "to_review":
      return row.image === "to_review" || row.report === "to_review";
    case "verified":
      return row.image === "verified_unchanged" || row.image === "verified_corrected";
    case "no_report":
      return row.report === "missing";
  }
}

function action(row: StudyRow): { label: MessageKey; to: string } {
  if (row.image === "to_review") return { label: "studies.action.review", to: `/weryfikacja/${row.id}` };
  if (row.report === "to_review") return { label: "studies.action.reviewReport", to: `/weryfikacja/${row.id}` };
  if (row.image?.startsWith("verified") || row.image === "saving") return { label: "studies.action.overview", to: `/badania/${row.id}` };
  return { label: "studies.action.details", to: `/badania?badanie=${row.id}` };
}

interface Props {
  rows: StudyRow[];
  selectedId: string | null;
  onSelect: (row: StudyRow) => void;
  onAttach: (row: StudyRow) => void;
  filter: Filter;
  onFilter: (filter: Filter) => void;
}

export default function StudiesTable({ rows, selectedId, onSelect, onAttach, filter, onFilter }: Props) {
  const [query, setQuery] = useState("");
  const visible = rows.filter((row) => matches(row, filter, query));

  return (
    <>
      <div className="studies__toolbar">
        <input
          className="input studies__search"
          type="search"
          placeholder={t("studies.search")}
          aria-label={t("studies.search")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="segmented" role="group" aria-label={t("studies.filter")}>
          {FILTERS.map((f) => (
            <button key={f.key} type="button" aria-pressed={filter === f.key} onClick={() => onFilter(f.key)}>
              {t(f.label)}
            </button>
          ))}
        </div>
        <span className="studies__count">
          {visible.length} {t("studies.count")}
        </span>
      </div>

      {visible.length === 0 ? (
        <p className="state">{t("studies.noMatch")}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t("studies.col.number")}</th>
              <th>{t("studies.col.patient")}</th>
              <th>{t("studies.col.date")}</th>
              <th>{t("studies.col.image")}</th>
              <th>{t("studies.col.report")}</th>
              <th className="cell-right">{t("studies.col.uncertainty")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => {
              const next = action(row);
              return (
                <tr
                  key={row.id}
                  className="is-clickable"
                  tabIndex={0}
                  aria-current={row.id === selectedId ? "true" : undefined}
                  onClick={() => onSelect(row)}
                  onKeyDown={(event) => event.key === "Enter" && onSelect(row)}
                >
                  <td className="cell-strong">
                    {row.image === "error" && <WarningIcon />}
                    {row.number ? `#${row.number}` : "—"}
                  </td>
                  <td>{row.patientId}</td>
                  <td>{row.studyDate ? formatDate(row.studyDate) : "—"}</td>
                  <td>{row.image ? <span className={IMAGE_CLASS[row.image]}>{t(`studies.image.${row.image}`)}</span> : "—"}</td>
                  <td>
                    {row.report ? (
                      <span className="studies__report">
                        <span className={REPORT_CLASS[row.report]}>{t(`studies.report.${row.report}`)}</span>
                        {row.report === "missing" && (
                          <button
                            type="button"
                            className="link"
                            onClick={(event) => {
                              event.stopPropagation();
                              onAttach(row);
                            }}
                          >
                            {t("studies.action.attach")}
                          </button>
                        )}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="cell-right">{row.uncertainty !== null ? formatDecimal(row.uncertainty) : "—"}</td>
                  <td className="cell-right">
                    {row.viewerUrl ? (
                      <a className="link" href={row.viewerUrl} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
                        {t("studies.openViewer")}
                      </a>
                    ) : (
                      <Link className="link" to={next.to} onClick={(event) => event.stopPropagation()}>
                        {t(next.label)}
                      </Link>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </>
  );
}
