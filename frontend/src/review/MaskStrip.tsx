import Hint from "../components/Hint";
import { t } from "../i18n";
import Icon from "../viewer/icons";

interface Props {
  corrected: boolean;
  // approved on its own: locked until the approval is taken back
  approved: boolean;
  // the model found nothing to segment
  empty?: boolean;
  // slices that differ from the model's mask in the main view
  edited: number;
  // empty slices between drawn ones, numbered from 0
  gaps: number[];
  version?: string;
  pending: boolean;
  onGoTo: (index: number) => void;
  onFill: () => void;
  onRestore: () => void;
  onApprove: () => void;
  onUnapprove: () => void;
  showMask: boolean;
  onToggleMask: () => void;
}

// only what is about the mask itself: its state, a gap to fill, the way back to the model's, approving it
export default function MaskStrip(props: Props) {
  const { corrected, approved, empty, edited, gaps, version, pending, onGoTo, onFill, onRestore, onApprove, onUnapprove, showMask, onToggleMask } = props;
  const state = approved ? "review.mask.approved" : corrected ? "review.mask.corrected" : empty ? "review.mask.empty" : "review.mask.proposed";
  return (
    <div className="mask-strip" aria-label={t("review.mask")}>
      <MaskToggle shown={showMask} onToggle={onToggleMask} />
      <span className={corrected && !approved ? "mask-strip__state mask-strip__state--corrected" : "mask-strip__state"} title={version && t("review.maskVersion", { v: version })}>
        {t(state)}
        {corrected && edited > 0 && <small> {t(edited === 1 ? "review.mask.onSlice" : "review.mask.onSlices", { n: edited })}</small>}
      </span>
      {!approved && gaps.length > 0 && (
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
        {approved ? (
          <button type="button" className="btn" disabled={pending} onClick={onUnapprove}>
            {t("review.mask.unapprove")}
          </button>
        ) : (
          <>
            {corrected && (
              <button type="button" className="link" onClick={onRestore}>
                {t("review.mask.restore")}
              </button>
            )}
            <button type="button" className="btn btn--confirm" disabled={pending} title={t("review.mask.approveTitle")} onClick={onApprove}>
              {t("review.mask.approve")}
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
      <kbd>M</kbd>
    </button>
  );
}
