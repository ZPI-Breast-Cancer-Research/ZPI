import Hint from "../components/Hint";
import { t } from "../i18n";
import Icon from "../viewer/icons";

interface Props {
  corrected: boolean;
  // slices that differ from the model's mask in the main view
  edited: number;
  // empty slices between drawn ones, numbered from 0
  gaps: number[];
  version?: string;
  onGoTo: (index: number) => void;
  onFill: () => void;
  onRestore: () => void;
  showMask: boolean;
  onToggleMask: () => void;
}

// only what is about the mask itself: its state, a gap to fill, the way back to the model's
export default function MaskStrip({ corrected, edited, gaps, version, onGoTo, onFill, onRestore, showMask, onToggleMask }: Props) {
  return (
    <div className="mask-strip" aria-label={t("review.mask")}>
      <span className={corrected ? "mask-strip__state mask-strip__state--corrected" : "mask-strip__state"} title={version && t("review.maskVersion", { v: version })}>
        {t(corrected ? "review.mask.corrected" : "review.mask.proposed")}
        {corrected && edited > 0 && <small> {t(edited === 1 ? "review.mask.onSlice" : "review.mask.onSlices", { n: edited })}</small>}
      </span>
      {gaps.length > 0 && (
        <span className="mask-strip__gap">
          {t(gaps.length === 1 ? "review.mask.gap" : "review.mask.gaps", { n: gaps.length })}{" "}
          <button type="button" className="link" onClick={() => onGoTo(gaps[0])}>
            {gaps[0] + 1}
          </button>
          {" · "}
          <Hint name={t("viewer.fill")} shortcut="I" text={t("viewer.hint.fill")} place="top">
            <button type="button" className="link" onClick={onFill}>
              {t(gaps.length === 1 ? "review.mask.fillGap" : "review.mask.fillGaps")}
            </button>
          </Hint>
        </span>
      )}
      <span className="mask-strip__end">
        {corrected && (
          <button type="button" className="link" onClick={onRestore}>
            {t("review.mask.restore")}
          </button>
        )}
        <MaskToggle shown={showMask} onToggle={onToggleMask} />
      </span>
    </div>
  );
}

export function MaskToggle({ shown, onToggle }: { shown: boolean; onToggle: () => void }) {
  return (
    <button type="button" className="mask-strip__eye" aria-pressed={shown} title={t("viewer.maskShown")} onClick={onToggle}>
      <Icon name="eye" />
      {!shown && t("viewer.maskHidden")}
      <kbd>M</kbd>
    </button>
  );
}
