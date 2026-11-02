import { init as coreInit, RenderingEngine, utilities as csUtils, type Types } from "@cornerstonejs/core";
import { init as loaderInit } from "@cornerstonejs/dicom-image-loader";
import {
  addTool,
  BrushTool,
  init as toolsInit,
  PanTool,
  ReferenceLinesTool,
  StackScrollTool,
  WindowLevelTool,
  ZoomTool,
} from "@cornerstonejs/tools";

import type { MaskSource } from "./types";

let ready = false;

export function initCornerstone() {
  if (ready) return;
  ready = true;
  coreInit();
  loaderInit({ maxWebWorkers: Math.max(1, Math.min(4, (navigator.hardwareConcurrency ?? 2) - 1)) });
  toolsInit();
  [PanTool, WindowLevelTool, StackScrollTool, ZoomTool, BrushTool, ReferenceLinesTool].forEach(addTool);
}

export const ENGINE_ID = "maria";
let engine: RenderingEngine | null = null;

// one engine for the whole app; a new one per viewer would lose the already loaded textures
export function getEngine() {
  initCornerstone();
  engine ??= new RenderingEngine(ENGINE_ID);
  return engine;
}

function ellipsoid(volume: Types.IImageVolume, source: MaskSource) {
  const center = source.center.map((f, axis) => f * (volume.dimensions[axis] - 1));
  const radius = source.radius.map((mm, axis) => mm / volume.spacing[axis]);
  const range = (axis: number) => [
    Math.max(0, Math.floor(center[axis] - radius[axis])),
    Math.min(volume.dimensions[axis] - 1, Math.ceil(center[axis] + radius[axis])),
  ];
  return { center, radius, range };
}

export function paintMask(labelmap: Types.IImageVolume, source: MaskSource) {
  const { center, radius, range } = ellipsoid(labelmap, source);
  const [[i0, i1], [j0, j1], [k0, k1]] = [range(0), range(1), range(2)];
  const voxels = labelmap.voxelManager!;
  voxels.clear();
  for (let k = k0; k <= k1; k++)
    for (let j = j0; j <= j1; j++)
      for (let i = i0; i <= i1; i++) {
        const d = ((i - center[0]) / radius[0]) ** 2 + ((j - center[1]) / radius[1]) ** 2 + ((k - center[2]) / radius[2]) ** 2;
        if (d < 1) voxels.setAtIJK(i, j, k, 1);
      }
}

export function maskCenterWorld(volume: Types.IImageVolume, source: MaskSource): Types.Point3 {
  const { center } = ellipsoid(volume, source);
  return csUtils.transformIndexToWorld(volume.imageData, center as Types.Point3);
}

export const historyMemo = csUtils.HistoryMemo.DefaultHistoryMemo;
