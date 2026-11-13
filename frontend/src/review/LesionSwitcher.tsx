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
  // one lesion still gets its heading, without arrows
  if (total === 1)
    return (
      <div className="lesion-switch lesion-switch--single">
        <div className="lesion-switch__body">
          <div className="lesion-switch__title">
            {t("row.section.lesion", { n: 1 })}
            {note && <span className="lesion-switch__note"> · {note}</span>}
          </div>
          <div className="lesion-switch__summary">{summary}</div>
        </div>
      </div>
    );
  return (
    <div className="lesion-switch">
      <button type="button" className="lesion-switch__arrow" aria-label={t("review.lesion.prev")} disabled={index === 0} onClick={onPrev}>
        ‹
      </button>
      <div className="lesion-switch__body">
        <div className="lesion-switch__title">
          {t("review.lesion.of", { n: index + 1, total })}
          {note && <span className="lesion-switch__note"> · {note}</span>}
        </div>
        <div className="lesion-switch__summary">{summary}</div>
      </div>
      <button type="button" className="lesion-switch__arrow" aria-label={t("review.lesion.next")} disabled={index === total - 1} onClick={onNext}>
        ›
      </button>
    </div>
  );
}
