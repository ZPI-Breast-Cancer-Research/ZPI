import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";

import { formatDayMonth, formatDecimal } from "../format";
import { t } from "../i18n";
import type { QueueEntry } from "./api";

interface Props {
  // what still waits; the case is verified by the mask and the form, never by this control
  waiting: { mask: boolean; fields: number };
  onShowMask: () => void;
  onShowFields: () => void;
  next: QueueEntry | null;
  // the few cases after this one; the full list lives in Badania
  upcoming: QueueEntry[];
  total: number;
  open: boolean;
  onOpen: (open: boolean) => void;
  onPickNext: (entry: QueueEntry) => void;
  onNext: () => void;
}

// the case's state in words and one way on: pink once the case is verified, quiet while something waits
export default function ApproveButton({ waiting, onShowMask, onShowFields, next, upcoming, total, open, onOpen, onPickNext, onNext }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const verified = !waiting.mask && waiting.fields === 0;

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => !box.current?.contains(event.target as Node) && onOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open, onOpen]);

  const fields = waiting.fields;
  return (
    <>
      {verified ? (
        <span className="approve-state approve-state--done">{t("review.verified")}</span>
      ) : (
        <span className="approve-state">
          {t("review.waiting")}{" "}
          {waiting.mask && (
            <button type="button" className="link" onClick={onShowMask}>
              {t("review.waiting.mask")}
            </button>
          )}
          {waiting.mask && fields > 0 && ", "}
          {fields > 0 && (
            <button type="button" className="link" onClick={onShowFields}>
              {t(fields === 1 ? "review.missing.field" : fields < 5 ? "review.missing.fewFields" : "review.missing.manyFields", { n: fields })}
            </button>
          )}
        </span>
      )}
      <div className={verified ? "approve" : "approve approve--quiet"} ref={box}>
        <button type="button" className="approve__main" title={t(verified ? "review.nextTitle" : "review.nextWaitingTitle")} onClick={onNext}>
          {next ? (
            <>
              {t("review.next")} <b>#{next.studyNumber}</b>
            </>
          ) : (
            t("review.finish")
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
              {t("review.nextCase")}
              <span>{t("review.uncertainty")}</span>
            </div>
            <ul role="listbox" aria-label={t("review.nextCase")}>
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
    </>
  );
}
