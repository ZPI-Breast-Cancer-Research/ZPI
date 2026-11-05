import { t } from "../i18n";
import type { BrushShape, Tool } from "./types";

export const RADIUS_MIN = 1;
export const RADIUS_MAX = 20;

interface Props {
  tool: Tool;
  shape: BrushShape;
  onShape: (shape: BrushShape) => void;
  radius: number;
  onRadius: (radius: number) => void;
  window: { width: number; center: number } | null;
  onResetWindow: () => void;
}

// options of the active tool, like the options bar in an image editor
export default function ToolOptions({ tool, shape, onShape, radius, onRadius, window, onResetWindow }: Props) {
  if (tool === "window") {
    return (
      <div className="tool-options">
        {window && <span>{t("viewer.windowValue", { w: Math.round(window.width), l: Math.round(window.center) })}</span>}
        <button type="button" className="btn btn--small" onClick={onResetWindow}>
          {t("viewer.windowReset")}
        </button>
      </div>
    );
  }
  if (tool === "pan") return <div className="tool-options" />;

  return (
    <div className="tool-options">
      <div className="segmented" role="group" title={t("viewer.shape")}>
        {(["circle", "sphere"] as BrushShape[]).map((s) => (
          <button key={s} type="button" aria-pressed={shape === s} onClick={() => onShape(s)}>
            <span className={`tool-options__shape tool-options__shape--${s}`} aria-hidden="true" />
            {t(`viewer.shape.${s}`)}
          </button>
        ))}
      </div>
      <span>{t("viewer.radius")}</span>
      <span className="tool-options__size" title={t("viewer.radiusTitle")}>
        <button type="button" aria-label={t("viewer.smaller")} disabled={radius <= RADIUS_MIN} onClick={() => onRadius(radius - 1)}>
          −
        </button>
        <b>{t("viewer.radiusValue", { n: radius })}</b>
        <button type="button" aria-label={t("viewer.bigger")} disabled={radius >= RADIUS_MAX} onClick={() => onRadius(radius + 1)}>
          +
        </button>
      </span>
    </div>
  );
}
