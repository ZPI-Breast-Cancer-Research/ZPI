import { useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { EmptyState } from "../components/State";
import WarningIcon from "../components/WarningIcon";
import { formatDate, formatDecimal, formatWhen, toIsoDate } from "../format";
import { plural, t, type MessageKey } from "../i18n";
import type { ImageStatus, ReportStatus, StudyRow } from "./api";

export type Filter = "all" | "processing" | "to_review" | "verified" | "no_report";
// which half of the case still waits, within "to review"
export type Part = "all" | "mask" | "report";

const PARTS: { key: Part; label: MessageKey }[] = [
  { key: "all", label: "studies.part.all" },
  { key: "mask", label: "studies.part.mask" },
  { key: "report", label: "studies.part.report" },
];

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

export function parsePart(value: string | null): Part {
  return value === "maska" ? "mask" : value === "opis" ? "report" : "all";
}

const imageVerified = (row: StudyRow) => row.image === "verified_unchanged" || row.image === "verified_corrected";

export function matches(row: StudyRow, filter: Filter, query = "", part: Part = "all"): boolean {
  const q = query.trim().toLowerCase();
  if (q && !`${row.number ?? ""} ${row.patientId}`.toLowerCase().includes(q)) return false;
  switch (filter) {
    case "all":
      return true;
    case "processing":
      return row.image === "queued" || row.image === "processing" || row.image === "saving";
    case "to_review":
      if (part === "mask") return row.image === "to_review";
      if (part === "report") return row.report === "to_review";
      return row.image === "to_review" || row.report === "to_review";
    case "verified":
      // like on the review screen: the mask and the form both done, or the mask alone when there's no report
      return imageVerified(row) && (row.report === "verified" || row.report === "missing");
    case "no_report":
      return row.report === "missing";
  }
}

function action(row: StudyRow, search: string): { label: MessageKey; to: string } {
  if (row.image === "to_review") return { label: "studies.action.review", to: `/weryfikacja/${row.id}` };
  if (row.report === "to_review") return { label: "studies.action.reviewReport", to: `/weryfikacja/${row.id}` };
  if (row.image?.startsWith("verified") || row.image === "saving") return { label: "studies.action.overview", to: `/badania/${row.id}` };
  // details stay on this list, so the filter stays too
  const params = new URLSearchParams(search);
  params.set("badanie", row.id);
  return { label: "studies.action.details", to: `/badania?${params}` };
}

interface Props {
  rows: StudyRow[];
  selectedId: string | null;
  onSelect: (row: StudyRow) => void;
  onAttach: (row: StudyRow) => void;
  filter: Filter;
  onFilter: (filter: Filter) => void;
  // with the verified filter: only what was verified today
  today: boolean;
  onToday: (today: boolean) => void;
  part: Part;
  onPart: (part: Part) => void;
}

export default function StudiesTable({ rows, selectedId, onSelect, onAttach, filter, onFilter, today, onToday, part, onPart }: Props) {
  const [query, setQuery] = useState("");
  const location = useLocation();
  const verified = filter === "verified";
  const todayIso = toIsoDate(new Date());
  const visible = rows
    .filter((row) => matches(row, filter, query, part))
    .filter((row) => !verified || !today || row.verifiedAt?.startsWith(todayIso))
    .sort((a, b) =>
      // to review: least certain first, the order verification follows; verified: latest first
      filter === "to_review"
        ? (b.uncertainty ?? -1) - (a.uncertainty ?? -1)
        : verified
          ? (b.verifiedAt ?? "").localeCompare(a.verifiedAt ?? "")
          : 0,
    );

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
        {filter === "to_review" && (
          <div className="segmented" role="group" aria-label={t("studies.part")}>
            {PARTS.map((p) => (
              <button key={p.key} type="button" aria-pressed={part === p.key} onClick={() => onPart(p.key)}>
                {t(p.label)}
              </button>
            ))}
          </div>
        )}
        {verified && (
          <div className="segmented" role="group" aria-label={t("studies.when")}>
            <button type="button" aria-pressed={today} onClick={() => onToday(true)}>
              {t("studies.today")}
            </button>
            <button type="button" aria-pressed={!today} onClick={() => onToday(false)}>
              {t("studies.anyDay")}
            </button>
          </div>
        )}
        <span className="studies__count">
          {plural(visible.length, "studies.count.one", "studies.count.few", "studies.count.many")}
        </span>
      </div>

      {visible.length === 0 ? (
        <EmptyState title={t("studies.noMatch")} />
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t("studies.col.number")}</th>
              <th>{t("studies.col.patient")}</th>
              <th>{t("studies.col.date")}</th>
              <th>{t("studies.col.image")}</th>
              <th>{t("studies.col.report")}</th>
              {verified ? (
                <th className="studies__sorted">{t("studies.col.verifiedAt")} ↓</th>
              ) : (
                <th className={filter === "to_review" ? "cell-right studies__sorted" : "cell-right"} title={filter === "to_review" ? t("studies.leastCertainFirst") : undefined}>
                  {t("studies.col.uncertainty")}
                  {filter === "to_review" && " ↓"}
                </th>
              )}
              <th />
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => {
              const next = action(row, location.search);
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
                  {verified ? (
                    <td>{row.verifiedAt ? formatWhen(row.verifiedAt) : "—"}</td>
                  ) : (
                    <td className="cell-right">{row.uncertainty !== null ? formatDecimal(row.uncertainty) : "—"}</td>
                  )}
                  <td className="cell-right">
                    <Link
                      className="link"
                      to={next.to}
                      // the case's "back" leads to this same list
                      state={{ from: location.pathname + location.search }}
                      onClick={(event) => event.stopPropagation()}
                    >
                      {t(next.label)}
                    </Link>
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
