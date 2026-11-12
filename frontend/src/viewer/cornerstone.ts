import { init as coreInit, RenderingEngine, utilities as csUtils } from "@cornerstonejs/core";
import { init as loaderInit } from "@cornerstonejs/dicom-image-loader";
import {
  addTool,
  BrushTool,
  init as toolsInit,
  PanTool,
  ReferenceLinesTool,
  WindowLevelTool,
  ZoomTool,
} from "@cornerstonejs/tools";


let ready = false;

export function initCornerstone() {
  if (ready) return;
  ready = true;
  coreInit();
  loaderInit({ maxWebWorkers: Math.max(1, Math.min(4, (navigator.hardwareConcurrency ?? 2) - 1)) });
  toolsInit();
  [PanTool, WindowLevelTool, ZoomTool, BrushTool, ReferenceLinesTool].forEach(addTool);
}

export const ENGINE_ID = "maria";
let engine: RenderingEngine | null = null;

// one engine for the whole app; a new one per viewer would lose the already loaded textures
export function getEngine() {
  initCornerstone();
  engine ??= new RenderingEngine(ENGINE_ID);
  return engine;
}

export const historyMemo = csUtils.HistoryMemo.DefaultHistoryMemo;
