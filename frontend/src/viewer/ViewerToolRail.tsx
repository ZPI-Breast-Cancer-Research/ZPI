import { t } from "../i18n";
import Icon from "./icons";
import type { Tool } from "./types";

interface Props {
  tool: Tool;
  onTool: (tool: Tool) => void;
  onUndo: () => void;
  canUndo: boolean;
  // the threshold brush reads the series on screen, which has to share the mask's grid
  thresholdOk: boolean;
  // filling between slices needs the mask on at least two of them
  canFill: boolean;
  filling: boolean;
  onFill: () => void;
}

export default function ViewerToolRail({ tool, onTool, onUndo, canUndo, thresholdOk, canFill, filling, onFill }: Props) {
  const toolButton = (name: Tool, label: string, title: string, disabled = false) => (
    <button type="button" className="tool-rail__btn" aria-pressed={tool === name} title={title} disabled={disabled} onClick={() => onTool(name)}>
      <Icon name={name} />
      {label}
    </button>
  );

  return (
    <nav className="tool-rail" aria-label={t("viewer.tools")}>
      {toolButton("brush", t("viewer.brush"), `${t("viewer.brush")} (B) · ${t("viewer.spaceHint")}`)}
      {toolButton("threshold", t("viewer.threshold"), thresholdOk ? t("viewer.thresholdTitle") : t("viewer.thresholdOff"), !thresholdOk)}
      {toolButton("eraser", t("viewer.eraser"), `${t("viewer.eraser")} (E)`)}
      <button type="button" className="tool-rail__btn" title={`${t("viewer.undo")} (Ctrl+Z)`} disabled={!canUndo} onClick={onUndo}>
        <Icon name="undo" />
        {t("viewer.undo")}
      </button>
      <button
        type="button"
        className="tool-rail__btn"
        title={canFill ? t("viewer.fillTitle") : t("viewer.fillOff")}
        disabled={!canFill || filling}
        aria-busy={filling}
        onClick={onFill}
      >
        <Icon name="fill" />
        {filling ? t("viewer.filling") : t("viewer.fill")}
      </button>
      {toolButton("pan", t("viewer.pan"), t("viewer.panTitle"))}
      {toolButton("window", t("viewer.window"), `${t("viewer.window")} (W)`)}
    </nav>
  );
}
