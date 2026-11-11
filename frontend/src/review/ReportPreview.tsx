import { plural, t } from "../i18n";
import type { CaseReport } from "./extraction";
import { fromExtraction } from "./report";
import { useUprightImage } from "./upright";

export default function ReportPreview({ report, onOpen }: { report: CaseReport; onOpen: () => void }) {
  const { result } = report;
  const image = useUprightImage(report.originalUrl, result.provenance.page_rotations[0] ?? 0);
  const model = result.data ? fromExtraction(result.data) : null;
  const conclusion = model?.conclusion;
  const lesions = model?.lesions.length ?? 0;

  return (
    <div className="report-scan">
      <button type="button" className="report-scan__thumb" title={t("review.original.openTitle")} onClick={onOpen}>
        {report.originalUrl ? (
          image && <img src={image} alt={t("review.original.title")} />
        ) : (
          <span className="report-scan__text">{result.text}</span>
        )}
        <span className="report-scan__open">⤢ {t("review.original.open")}</span>
      </button>
      <div className="report-scan__line">
        <span>
          <span className="muted">{t("review.original.conclusion")}</span>{" "}
          {[conclusion?.birads && `BI-RADS ${conclusion.birads}`, conclusion?.recommendation].filter(Boolean).join(" · ") || "—"}
        </span>
        <span className="muted">{plural(lesions, "review.original.lesions.one", "review.original.lesions.few", "review.original.lesions.many")}</span>
      </div>
    </div>
  );
}
