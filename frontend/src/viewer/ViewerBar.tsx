import type { ReactNode } from "react";

import { t } from "../i18n";
import type { Series } from "./types";

interface Props {
  // left: what the active tool can do; right: which series is under the mask
  children?: ReactNode;
  series: Series;
  onSeries: (series: Series) => void;
  available: Series[];
}

export default function ViewerBar({ children, series, onSeries, available }: Props) {
  return (
    <div className="viewer-bar">
      {children}
      <div className="segmented viewer-bar__series" role="radiogroup" aria-label={t("viewer.series")}>
        {(["post", "sub", "pre"] as Series[]).map((s) => (
          <button
            key={s}
            type="button"
            role="radio"
            aria-checked={series === s}
            aria-pressed={series === s}
            disabled={!available.includes(s)}
            onClick={() => onSeries(s)}
          >
            {t(`viewer.series.${s}`)}
          </button>
        ))}
      </div>
    </div>
  );
}
