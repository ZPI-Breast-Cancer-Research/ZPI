import { t } from "../i18n";

interface Props {
  index: number;
  total: number;
  summary: string;
  note: string | null;
  onPrev: () => void;
  onNext: () => void;
}

export default function LesionSwitcher({ index, total, summary, note, onPrev, onNext }: Props) {
  return (
    <div className="lesion-switch">
      <button type="button" className="lesion-switch__arrow" aria-label={t("review.lesion.prev")} disabled={index === 0} onClick={onPrev}>
        ‹
      </button>
      <div className="lesion-switch__body">
        <div>
          {t("review.lesion.of", { n: index + 1, total })} · {summary}
        </div>
        {note && <div className="lesion-switch__note">{note}</div>}
      </div>
      <button type="button" className="lesion-switch__arrow" aria-label={t("review.lesion.next")} disabled={index === total - 1} onClick={onNext}>
        ›
      </button>
    </div>
  );
}
