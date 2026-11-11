import { t } from "../i18n";

interface Props {
  index: number;
  total: number;
  summary: string;
  note: string;
  onImage: boolean;
  onPrev: () => void;
  onNext: () => void;
  // only when the match with the image is a guess
  onMarkOnImage?: () => void;
}

export default function LesionSwitcher({ index, total, summary, note, onImage, onPrev, onNext, onMarkOnImage }: Props) {
  return (
    <div className="lesion-switch">
      <button type="button" className="lesion-switch__arrow" aria-label={t("review.lesion.prev")} disabled={index === 0} onClick={onPrev}>
        ‹
      </button>
      <div className="lesion-switch__body">
        <div>
          {t("review.lesion.of", { n: index + 1, total })} · {summary}
        </div>
        <div className={onImage ? "lesion-switch__note lesion-switch__note--image" : "lesion-switch__note"}>
          {note}
          {onMarkOnImage && (
            <>
              {" · "}
              <button type="button" className="link" onClick={onMarkOnImage}>
                {t("review.lesion.markOnImage")}
              </button>
            </>
          )}
        </div>
      </div>
      <button type="button" className="lesion-switch__arrow" aria-label={t("review.lesion.next")} disabled={index === total - 1} onClick={onNext}>
        ›
      </button>
    </div>
  );
}
