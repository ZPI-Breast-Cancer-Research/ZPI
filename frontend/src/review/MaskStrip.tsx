import { formatMetric } from "../format";
import { t } from "../i18n";
import Icon from "../viewer/icons";
import type { MaskState } from "../viewer/types";
import type { ReviewCase } from "./api";

interface Props {
  state: MaskState;
  measurements: ReviewCase["measurements"];
  version?: string;
  onConfirm: () => void;
  onRestore: () => void;
  showMask: boolean;
  onToggleMask: () => void;
}

export default function MaskStrip({ state, measurements, version, onConfirm, onRestore, showMask, onToggleMask }: Props) {
  return (
    <div className="mask-strip" aria-label={t("review.mask")}>
      <span className="mask-strip__label">{t("review.mask")}</span>
      {version && <span className="muted">{t("review.maskVersion", { v: version })}</span>}
      <MaskToggle shown={showMask} onToggle={onToggleMask} />
      {state === "corrected" ? (
        <span className="muted">{t("review.mask.recalc")}</span>
      ) : (
        <>
          <span>
            {t("review.mask.volume")} <b>{formatMetric(measurements.volume, " cm³")}</b>
          </span>
          <span>
            {t("review.mask.size")} <b>{formatMetric(measurements.size, " mm")}</b>
          </span>
        </>
      )}
      <span>
        {t("review.mask.inReport")} <b>{formatMetric(measurements.sizeInReport, " mm")}</b>
      </span>
      <span className="mask-strip__end">
        {state === "proposed" && (
          <>
            <span className="status">{t("review.mask.proposed")}</span>
            <button type="button" className="btn" onClick={onConfirm}>
              {t("review.mask.confirm")}
            </button>
          </>
        )}
        {state === "confirmed" && <span className="status status--confirmed">{t("review.mask.confirmed")}</span>}
        {state === "corrected" && (
          <>
            <span className="status status--corrected">{t("review.mask.corrected")}</span>
            <button type="button" className="link" onClick={onRestore}>
              {t("review.mask.restore")}
            </button>
          </>
        )}
      </span>
    </div>
  );
}

export function MaskToggle({ shown, onToggle }: { shown: boolean; onToggle: () => void }) {
  return (
    <button type="button" className="mask-strip__eye" aria-pressed={shown} title={t("viewer.maskShown")} onClick={onToggle}>
      <Icon name="eye" />
      {!shown && t("viewer.maskHidden")}
    </button>
  );
}
