import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";

import { formatDayMonth, formatDecimal } from "../format";
import { t } from "../i18n";
import type { QueueEntry } from "./api";

interface Props {
  // fields still to be checked before approving; zero means ready
  missingFields: number;
  onMissingFields: () => void;
  next: QueueEntry | null;
  // the few cases after this one; the full list lives in Badania
  upcoming: QueueEntry[];
  total: number;
  open: boolean;
  onOpen: (open: boolean) => void;
  onPickNext: (entry: QueueEntry) => void;
  onApprove: () => void;
  pending: boolean;
}

// one control for "approve and go on": the main part approves, the arrow picks where to go next
export default function ApproveButton({ missingFields, onMissingFields, next, upcoming, total, open, onOpen, onPickNext, onApprove, pending }: Props) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => !box.current?.contains(event.target as Node) && onOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open, onOpen]);

  if (missingFields) {
    return (
      <span className="approve approve--missing">
        {t("review.missing")}{" "}
        <button type="button" className="link" onClick={onMissingFields}>
          {t(missingFields === 1 ? "review.missing.field" : missingFields < 5 ? "review.missing.fewFields" : "review.missing.manyFields", { n: missingFields })}
        </button>
      </span>
    );
  }

  return (
    <div className="approve" ref={box}>
      <button type="button" className="approve__main" disabled={pending} title={t("review.approveTitle")} onClick={onApprove}>
        {next ? (
          <>
            {t("review.approveNext")} <b>#{next.studyNumber}</b>
          </>
        ) : (
          t("review.approveLast")
        )}
      </button>
      {next && (
        <button
          type="button"
          className="approve__more"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label={t("review.pickNext")}
          title={`${t("review.pickNext")} (N)`}
          onClick={() => onOpen(!open)}
        >
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M4 6l4 4 4-4" />
          </svg>
        </button>
      )}
      {open && next && (
        <div className="approve__menu">
          <div className="approve__menu-head">
            {t("review.afterApprove")}
            <span>{t("review.uncertainty")}</span>
          </div>
          <ul role="listbox" aria-label={t("review.afterApprove")}>
            {upcoming.map((entry) => (
              <li key={entry.studyId}>
                <button
                  type="button"
                  role="option"
                  aria-selected={entry.studyId === next.studyId}
                  onClick={() => {
                    onPickNext(entry);
                    onOpen(false);
                  }}
                >
                  <b>#{entry.studyNumber}</b>
                  <span className="muted">{formatDayMonth(entry.studyDate)}</span>
                  <span className="approve__menu-value">{formatDecimal(entry.uncertainty)}</span>
                </button>
              </li>
            ))}
          </ul>
          <Link className="link approve__menu-all" to="/badania?filtr=to_review">
            {t("review.allToReview", { n: total })}
          </Link>
        </div>
      )}
    </div>
  );
}
