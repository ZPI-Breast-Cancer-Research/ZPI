import type { Dispatch, ReactNode, SetStateAction } from "react";

import { t } from "../i18n";
import Icon from "./icons";
import type { Layout } from "./layout";
import type { Series } from "./types";

// three views or only the main one (V); the icon shows what a click switches to
export function LayoutButton({ layout, onLayout }: { layout: Layout; onLayout: Dispatch<SetStateAction<Layout>> }) {
  const label = t(layout.single ? "viewer.layout.toThree" : "viewer.layout.toOne");
  return (
    <button type="button" title={label} aria-label={label} onClick={() => onLayout((l) => ({ ...l, single: !l.single }))}>
      <Icon name={layout.single ? "three" : "one"} />
    </button>
  );
}

interface Props {
  // left: what the active tool can do; right: which series is under the mask
  children?: ReactNode;
  series: Series;
  onSeries: (series: Series) => void;
  available: Series[];
  // icon buttons in the corner that change the screen layout
  corner?: ReactNode;
}

export default function ViewerBar({ children, series, onSeries, available, corner }: Props) {
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
      {corner && <div className="viewer-bar__corner">{corner}</div>}
    </div>
  );
}
