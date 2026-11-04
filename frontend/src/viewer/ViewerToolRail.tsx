import Hint from "../components/Hint";
import { t } from "../i18n";
import Icon from "./icons";
import type { Tool } from "./types";

interface Props {
  tool: Tool;
  onTool: (tool: Tool) => void;
  onUndo: () => void;
  canUndo: boolean;
  // the edge brush reads the series on screen, which has to share the mask's grid
  thresholdOk: boolean;
  // filling between slices needs the mask on at least two of them
  canFill: boolean;
  filling: boolean;
  onFill: () => void;
  // the slice on screen differs from the model's mask
  canRestoreSlice: boolean;
  onRestoreSlice: () => void;
}

const KEYS: Record<Tool, string> = { pan: "P", window: "W", brush: "B", threshold: "T", eraser: "E" };

// greyed buttons stay hoverable (aria-disabled), so their hint still shows
export default function ViewerToolRail({ tool, onTool, onUndo, canUndo, thresholdOk, canFill, filling, onFill, canRestoreSlice, onRestoreSlice }: Props) {
  const button = (key: Tool | "fill" | "undo" | "slice", name: string, shortcut: string, label: string, onClick: () => void, state: { pressed?: boolean; off?: boolean; busy?: boolean } = {}) => (
    <Hint name={name} shortcut={shortcut} text={t(`viewer.hint.${key}`)}>
      <button
        type="button"
        className="tool-rail__btn"
        aria-label={name}
        aria-pressed={state.pressed}
        aria-disabled={state.off || undefined}
        aria-busy={state.busy || undefined}
        onClick={() => !state.off && onClick()}
      >
        <Icon name={key} />
        <span className="tool-rail__label">{label}</span>
      </button>
    </Hint>
  );
  const toolButton = (name: Tool, off = false) =>
    button(name, t(`viewer.${name}`), KEYS[name], t(name === "threshold" ? "viewer.thresholdLabel" : `viewer.${name}`), () => onTool(name), {
      pressed: tool === name,
      off,
    });

  return (
    <nav className="tool-rail" aria-label={t("viewer.tools")}>
      {toolButton("pan")}
      {toolButton("window")}
      <span className="tool-rail__gap" aria-hidden="true" />
      {toolButton("brush")}
      {toolButton("threshold", !thresholdOk)}
      {toolButton("eraser")}
      <span className="tool-rail__gap" aria-hidden="true" />
      {button("fill", t("viewer.fill"), "I", filling ? t("viewer.filling") : t("viewer.fill"), onFill, { off: !canFill || filling, busy: filling })}
      {button("undo", t("viewer.undo"), "Ctrl+Z", t("viewer.undo"), onUndo, { off: !canUndo })}
      {button("slice", t("viewer.restoreSlice"), "R", t("viewer.restoreSlice"), onRestoreSlice, { off: !canRestoreSlice })}
    </nav>
  );
}
