import { t } from "../i18n";
import type { Series, Tool } from "./types";

const ICONS: Record<string, JSX.Element> = {
  brush: <path d="M10.5 2.5l3 3-6.5 6.5H4V9z M9 4l3 3" />,
  eraser: <path d="M6 13.5h7.5 M2.5 10l6-6.5 4.5 4.5-5.5 5.5H6z M5.5 7l4.5 4.5" />,
  undo: <path d="M4.5 6.5h6a3.5 3.5 0 0 1 0 7H7 M7 3.5l-3 3 3 3" />,
  pan: <path d="M8 1.5v13 M1.5 8h13 M6 3.5l2-2 2 2 M6 12.5l2 2 2-2 M3.5 6l-2 2 2 2 M12.5 6l2 2-2 2" />,
  window: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 2a6 6 0 0 1 0 12z" fill="currentColor" stroke="none" />
    </>
  ),
  eye: (
    <>
      <path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" />
      <circle cx="8" cy="8" r="2" />
    </>
  ),
};

const Icon = ({ name }: { name: string }) => (
  <svg viewBox="0 0 16 16" aria-hidden="true">
    {ICONS[name]}
  </svg>
);

interface Props {
  tool: Tool;
  onTool: (tool: Tool) => void;
  onUndo: () => void;
  canUndo: boolean;
  showMask: boolean;
  onToggleMask: () => void;
  series: Series;
  onSeries: (series: Series) => void;
}

export default function ViewerToolbar({ tool, onTool, onUndo, canUndo, showMask, onToggleMask, series, onSeries }: Props) {
  return (
    <div className="viewer-toolbar" role="toolbar" aria-label={t("viewer.tools")}>
      <div className="viewer-toolbar__group">
        <button type="button" aria-pressed={tool === "brush"} title={`${t("viewer.brush")} (B)`} onClick={() => onTool("brush")}>
          <Icon name="brush" />
          {t("viewer.brush")}
        </button>
        <button type="button" aria-pressed={tool === "eraser"} title={`${t("viewer.eraser")} (E)`} onClick={() => onTool("eraser")}>
          <Icon name="eraser" />
          {t("viewer.eraser")}
        </button>
        <button type="button" title={`${t("viewer.undo")} (Ctrl+Z)`} aria-label={t("viewer.undo")} disabled={!canUndo} onClick={onUndo}>
          <Icon name="undo" />
        </button>
      </div>
      <div className="viewer-toolbar__group">
        <button type="button" aria-pressed={tool === "pan"} title={`${t("viewer.pan")} (P)`} aria-label={t("viewer.pan")} onClick={() => onTool("pan")}>
          <Icon name="pan" />
        </button>
        <button type="button" aria-pressed={tool === "window"} title={`${t("viewer.window")} (W)`} aria-label={t("viewer.window")} onClick={() => onTool("window")}>
          <Icon name="window" />
        </button>
      </div>
      <div className="viewer-toolbar__group">
        <button type="button" aria-pressed={showMask} title={`${t("viewer.mask")} (M)`} onClick={onToggleMask}>
          <Icon name="eye" />
          {t("viewer.mask")}
        </button>
      </div>
      <div className="segmented" role="radiogroup" aria-label={t("viewer.series")}>
        {(["post", "sub", "pre"] as Series[]).map((s) => (
          <button key={s} type="button" role="radio" aria-checked={series === s} aria-pressed={series === s} onClick={() => onSeries(s)}>
            {t(`viewer.series.${s}`)}
          </button>
        ))}
      </div>
    </div>
  );
}
