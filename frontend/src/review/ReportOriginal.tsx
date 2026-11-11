import { useEffect, useRef, useState } from "react";

import { t } from "../i18n";
import type { CaseReport, ExtractionResult } from "./extraction";
import ReportText from "./ReportText";
import { useUprightImage } from "./upright";

// the uploaded file and, once the worker has read it, its result
export interface Scan {
  url: string | null;
  fileName: string;
  result: ExtractionResult | null;
}

export const scanOf = (report: CaseReport): Scan => ({ url: report.originalUrl, fileName: report.result.source, result: report.result });

interface Props {
  scan: Scan;
  open: boolean;
  onClose: () => void;
  lesion: { number: number; quotes: string[] } | null;
  onPrev?: () => void;
  onNext?: () => void;
}

const ZOOMS = [50, 75, 100, 125, 150, 200, 300];

// native dialog: Esc, focus and the backdrop for free
export default function ReportOriginal({ scan, open, onClose, lesion, onPrev, onNext }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const textFile = /\.txt$/i.test(scan.fileName);
  const photo = !!scan.url && !textFile;
  const [tab, setTab] = useState<"photo" | "text">(photo ? "photo" : "text");
  const [turn, setTurn] = useState(0);
  const [zoom, setZoom] = useState(100);
  const [fileText, setFileText] = useState<string | null>(null);
  const image = useUprightImage(photo ? scan.url : null, (scan.result?.provenance.page_rotations[0] ?? 0) + turn);
  const text = scan.result?.text ?? fileText;

  // a .txt nobody has read yet is shown as it was uploaded
  useEffect(() => {
    if (!open || !textFile || scan.result || !scan.url || fileText !== null) return;
    fetch(scan.url)
      .then((response) => (response.ok ? response.text() : ""))
      .then(setFileText, () => setFileText(""));
  }, [open, textFile, scan.result, scan.url, fileText]);

  useEffect(() => {
    const box = dialog.current;
    if (!box) return;
    if (open && !box.open) box.showModal();
    if (!open && box.open) box.close();
  }, [open]);

  const step = (by: number) => setZoom((z) => ZOOMS[Math.max(0, Math.min(ZOOMS.length - 1, ZOOMS.indexOf(z) + by))]);

  // Ctrl + wheel (and a trackpad pinch) zooms the scan, like in the viewer
  useEffect(() => {
    const box = body.current;
    if (!box || tab !== "photo") return;
    // a pinch sends many tiny events; one zoom step per this much of them
    let total = 0;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      total += event.deltaY;
      if (Math.abs(total) < 40) return;
      step(total < 0 ? 1 : -1);
      total = 0;
    };
    box.addEventListener("wheel", onWheel, { passive: false });
    return () => box.removeEventListener("wheel", onWheel);
  }, [tab, open]);

  return (
    <dialog
      ref={dialog}
      className="original"
      aria-label={t("review.original.title")}
      onClose={onClose}
      onClick={(event) => event.target === dialog.current && onClose()}
    >
      <div className="original__head">
        <span>
          {t("review.original.title")} <span className="muted">· {scan.fileName}</span>
        </span>
        <div className="original__tools">
          {tab === "photo" && photo && (
            <>
              <button type="button" className="btn btn--small" onClick={() => setTurn((a) => a + 90)}>
                ↺ {t("review.original.rotateLeft")}
              </button>
              <button type="button" className="btn btn--small" onClick={() => setTurn((a) => a - 90)}>
                ↻ {t("review.original.rotateRight")}
              </button>
              <button type="button" className="btn btn--small" aria-label={t("review.original.zoomOut")} onClick={() => step(-1)}>
                −
              </button>
              <span className="original__zoom">{zoom}%</span>
              <button type="button" className="btn btn--small" aria-label={t("review.original.zoomIn")} onClick={() => step(1)}>
                +
              </button>
            </>
          )}
          <button type="button" className="btn btn--small" onClick={onClose}>
            ✕ {t("review.original.close")}
          </button>
        </div>
      </div>
      <nav className="tabs original__tabs" aria-label={t("review.original.title")}>
        {photo && (
          <a href="#zdjecie" className={tab === "photo" ? "active" : undefined} onClick={(e) => (e.preventDefault(), setTab("photo"))}>
            {t("review.original.photo")}
          </a>
        )}
        {text !== null && (
          <a href="#tekst" className={tab === "text" ? "active" : undefined} onClick={(e) => (e.preventDefault(), setTab("text"))}>
            {t("review.original.text")}
          </a>
        )}
      </nav>
      <div className="original__body" ref={body}>
        {tab === "photo" && photo ? (
          image && <img src={image} alt={t("review.original.title")} style={{ width: `${zoom}%` }} />
        ) : (
          <>
            {!photo && scan.result && <p className="note">{t("review.original.noPhoto")}</p>}
            {text !== null && <ReportText text={text} quotes={lesion ? lesion.quotes : []} />}
          </>
        )}
      </div>
      {tab === "text" && lesion && (onPrev || onNext) && (
        <div className="original__foot">
          <span className="muted">{t("review.original.textNote", { n: lesion.number })}</span>
          <span>
            <button type="button" className="btn btn--small" disabled={!onPrev} onClick={onPrev}>
              ‹ {t("review.lesion.prev")}
            </button>{" "}
            <button type="button" className="btn btn--small" disabled={!onNext} onClick={onNext}>
              {t("review.lesion.next")} ›
            </button>
          </span>
        </div>
      )}
    </dialog>
  );
}
