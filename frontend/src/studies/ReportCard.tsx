import { useState, type ReactNode } from "react";

import { formatDate } from "../format";
import { t } from "../i18n";
import ReportOriginal from "../review/ReportOriginal";
import { fromExtraction } from "../review/report";
import { useUprightImage } from "../review/upright";
import type { UnassignedReport } from "./api";
import "../review/review.css";

interface Props {
  item: UnassignedReport;
  selected?: boolean;
  onSelect?: () => void;
  // a bigger look at the report while the card is open
  preview?: boolean;
  // shown under the card while it is selected
  children?: ReactNode;
}

function summary(item: UnassignedReport) {
  const result = item.report?.result;
  if (!result) return null;
  if (result.status === "error" || !result.data) return t("studies.card.failed");
  const { conclusion, lesions } = fromExtraction(result.data);
  const parts = [conclusion.birads && `BI-RADS ${conclusion.birads}`, conclusion.recommendation];
  return parts.filter(Boolean).join(" · ") || t("studies.card.lesions", { n: lesions.length });
}

export default function ReportCard({ item, selected = false, onSelect, preview = false, children }: Props) {
  const [open, setOpen] = useState(false);
  const result = item.report?.result ?? null;
  const url = item.report?.originalUrl ?? item.originalUrl;
  const photo = item.kind === "scan" && !!url;
  const thumb = useUprightImage(photo ? url : null, result?.provenance.page_rotations[0] ?? 0);
  const canOpen = !!url || !!result;

  return (
    <div className={selected ? "report-card report-card--selected" : "report-card"}>
      <div className="report-card__row">
        <button type="button" className="report-card__main" aria-pressed={selected} onClick={onSelect}>
          <span className="report-card__thumb">{photo && thumb ? <img src={thumb} alt="" /> : <span className="file-tag__ext">{item.fileName.split(".").pop()?.toUpperCase().slice(0, 4)}</span>}</span>
          <span className="report-card__text">
            <span className="report-card__name">{item.fileName}</span>
            <span className="report-card__meta">
              {[summary(item), item.addedAt && t("studies.card.added", { date: formatDate(item.addedAt) })].filter(Boolean).join(" · ")}
            </span>
          </span>
        </button>
        {canOpen && (
          <button type="button" className="report-card__open" title={t("studies.card.open")} aria-label={t("studies.card.open")} onClick={() => setOpen(true)}>
            ⤢
          </button>
        )}
      </div>
      {selected && preview && canOpen && (
        <div className="report-card__preview">
          <button type="button" className="report-scan__thumb" title={t("studies.card.open")} onClick={() => setOpen(true)}>
            {photo ? thumb && <img src={thumb} alt={t("review.original.title")} /> : <span className="report-scan__text">{result?.text ?? item.fileName}</span>}
            <span className="report-scan__open">⤢ {t("review.original.open")}</span>
          </button>
        </div>
      )}
      {selected && children}
      {canOpen && <ReportOriginal scan={{ url, fileName: item.fileName, result }} open={open} onClose={() => setOpen(false)} lesion={null} />}
    </div>
  );
}
