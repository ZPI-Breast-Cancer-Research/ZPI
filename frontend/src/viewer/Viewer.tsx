import { cache, Enums, eventTarget, setVolumesForViewports, utilities as csUtils, volumeLoader, type Types } from "@cornerstonejs/core";
import {
  BrushTool,
  Enums as ToolEnums,
  PanTool,
  ReferenceLinesTool,
  segmentation,
  ToolGroupManager,
  utilities as toolUtils,
  WindowLevelTool,
  ZoomTool,
} from "@cornerstonejs/tools";
import { forwardRef, useEffect, useId, useImperativeHandle, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";

import { formatOneDecimal } from "../format";
import { t } from "../i18n";
import { ENGINE_ID, getEngine, historyMemo, maskCenterWorld, paintMask } from "./cornerstone";
import { DicomWebError, findSeries, seriesImageIds } from "./dicomweb";
import type { Layout } from "./layout";
import { interpolateMask, maskExtent, restoreSlice, type Extent } from "./maskTools";
import SliceStrip from "./SliceStrip";
import type { BrushShape, MaskSource, MaskState, Plane, Series, Tool } from "./types";
import "./viewer.css";

const ERASER = "Eraser";
const THRESHOLD = "ThresholdBrush";
const STRATEGY: Record<BrushShape, Record<"brush" | "threshold" | "eraser", string>> = {
  circle: { brush: "FILL_INSIDE_CIRCLE", threshold: "THRESHOLD_INSIDE_CIRCLE", eraser: "ERASE_INSIDE_CIRCLE" },
  sphere: { brush: "FILL_INSIDE_SPHERE", threshold: "THRESHOLD_INSIDE_SPHERE", eraser: "ERASE_INSIDE_SPHERE" },
};
const Labelmap = ToolEnums.SegmentationRepresentations.Labelmap;
const PINK: Types.Color = [236, 111, 152, 255];
const LIGHT: Types.Color = [232, 236, 241, 255];
const PLANES: Plane[] = ["axial", "sagittal", "coronal"];
const ORIENTATION: Record<Plane, Enums.OrientationAxis> = {
  axial: Enums.OrientationAxis.AXIAL,
  sagittal: Enums.OrientationAxis.SAGITTAL,
  coronal: Enums.OrientationAxis.CORONAL,
};
// the same planes snapped to the study's own grid, so a slice on screen is exactly one layer of voxels
const ALIGNED: Record<Plane, Enums.OrientationAxis> = {
  axial: Enums.OrientationAxis.AXIAL_REFORMAT,
  sagittal: Enums.OrientationAxis.SAGITTAL_REFORMAT,
  coronal: Enums.OrientationAxis.CORONAL_REFORMAT,
};
// a trackpad sends many small wheel events; one slice per this much scrolling
const WHEEL_STEP = 60;

type Problem = DicomWebError["kind"] | "no-study";

interface Props {
  studyUid: string | null;
  // the mask on screen (editable in review) and, optionally, the model's own mask drawn as an outline
  mask: MaskSource | null;
  modelMask?: MaskSource | null;
  series: Series;
  maskState: MaskState;
  showMask: boolean;
  tool?: Tool;
  editable?: boolean;
  modelOutline?: boolean;
  brushShape?: BrushShape;
  // radius in mm, so the brush covers the same tissue at any zoom
  brushRadius?: number;
  onEdit?: () => void;
  onSeriesFound?: (available: Series[]) => void;
  // false when the series on screen has a different grid than the mask
  onGridMatch?: (same: boolean) => void;
  onWindow?: (window: { width: number; center: number }) => void;
  // where the mask is on the main plane and how it differs from the model's, after every change
  onMaskInfo?: (info: MaskInfo) => void;
  // which plane is big and whether the others show; the page keeps it (useViewerLayout)
  layout: Layout;
  onLayout: Dispatch<SetStateAction<Layout>>;
}

export interface MaskInfo {
  slices: number;
  gaps: number[];
  edited: number;
  // the slice on screen in the main view differs from the model's mask
  currentEdited: boolean;
  sizeMm: number | null;
}

export interface ViewerHandle {
  undo: () => void;
  restoreModel: () => void;
  resetWindow: () => void;
  // fills the slices between the drawn ones; resolves false when there was nothing to fill
  interpolate: () => Promise<boolean>;
  // the model's mask back on the main view's current slice; false when it already matched
  restoreSlice: () => boolean;
  goToSlice: (index: number) => void;
}

async function loadVolume(studyUid: string, seriesUid: string) {
  const volumeId = `cornerstoneStreamingImageVolume:${seriesUid}`;
  if (!cache.getVolume(volumeId)) {
    const imageIds = await seriesImageIds(studyUid, seriesUid);
    if (imageIds.length < 2) throw new DicomWebError("single-image");
    const volume = await volumeLoader.createAndCacheVolume(volumeId, { imageIds });
    (volume as Types.IStreamingImageVolume).load();
  }
  return cache.getVolume(volumeId);
}

function addMask(segmentationId: string, volume: Types.IImageVolume, source: MaskSource | null) {
  const labelmap = volumeLoader.createAndCacheDerivedLabelmapVolume(volume.volumeId, { volumeId: segmentationId });
  if (source) paintMask(labelmap, source);
  segmentation.addSegmentations([{ segmentationId, representation: { type: Labelmap, data: { volumeId: segmentationId } } }]);
}

function sameGrid(a: Types.IImageVolume, b: Types.IImageVolume) {
  const close = (x: ArrayLike<number>, y: ArrayLike<number>) => Array.from(x).every((v, i) => Math.abs(v - y[i]) < 1e-3);
  return close(a.dimensions, b.dimensions) && close(a.spacing, b.spacing) && close(a.direction, b.direction) && close(a.origin, b.origin);
}

function removeMask(segmentationId: string) {
  if (segmentation.state.getSegmentation(segmentationId)) segmentation.removeSegmentation(segmentationId);
  if (cache.getVolume(segmentationId)) cache.removeVolumeLoadObject(segmentationId);
}

// slice index of a world point in this viewport, plus the slice spacing
function sliceOf(viewport: Types.IVolumeViewport, world: Types.Point3) {
  const camera = viewport.getCamera();
  const { spacingInNormalDirection } = csUtils.getTargetVolumeAndSpacingInNormalDir(viewport, camera);
  const offset = [0, 1, 2].reduce((sum, a) => sum + (world[a] - camera.focalPoint![a]) * camera.viewPlaneNormal![a], 0);
  const now = csUtils.getImageSliceDataForVolumeViewport(viewport)!;
  const index = Math.max(0, Math.min(now.numberOfSlices - 1, now.imageIndex + Math.round(offset / spacingInNormalDirection)));
  return { index, spacing: spacingInNormalDirection };
}

const Viewer = forwardRef<ViewerHandle, Props>(function Viewer(
  {
    studyUid,
    mask,
    modelMask = null,
    series,
    maskState,
    showMask,
    tool = "window",
    editable = false,
    modelOutline = false,
    brushShape = "circle",
    brushRadius = 5,
    onEdit,
    onSeriesFound,
    onGridMatch,
    onWindow,
    onMaskInfo,
    layout,
    onLayout: setLayout,
  },
  ref,
) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const ids = useMemo(
    () => ({
      axial: `axial-${uid}`,
      sagittal: `sagittal-${uid}`,
      coronal: `coronal-${uid}`,
      tools: `tools-${uid}`,
      mask: `mask-${uid}`,
      model: `model-${uid}`,
    }),
    [uid],
  );
  const rootEl = useRef<HTMLDivElement>(null);
  const els = useRef<Record<Plane, HTMLDivElement | null>>({ axial: null, sagittal: null, coronal: null });
  const engine = useRef<ReturnType<typeof getEngine> | null>(null);
  const seriesUids = useRef<Partial<Record<Series, string>>>({});
  const editing = useRef<{ changed: boolean } | null>(null);
  const hovered = useRef<Plane | null>(null);
  // a plane's camera scale from before the user zoomed or panned it; none means it still fits the view
  const fitScale = useRef<Partial<Record<Plane, number>>>({});
  const panning = useRef(false);
  const callbacks = useRef({ onEdit, onSeriesFound, onGridMatch, onWindow, onMaskInfo });
  callbacks.current = { onEdit, onSeriesFound, onGridMatch, onWindow, onMaskInfo };
  // the mask as the model drew it, to tell which slices the radiologist changed
  const original = useRef<Uint8Array | null>(null);

  const [problem, setProblem] = useState<Problem | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [shown, setShown] = useState<Series | null>(null);
  const [slices, setSlices] = useState<Record<Plane, { index: number; count: number }>>({
    axial: { index: 0, count: 0 },
    sagittal: { index: 0, count: 0 },
    coronal: { index: 0, count: 0 },
  });
  // the window was dragged away from the study's own; offers a way back in the header
  const [windowChanged, setWindowChanged] = useState(false);
  const [zoom, setZoom] = useState<number | null>(null);
  const [extents, setExtents] = useState<Partial<Record<Plane, Extent>>>({});
  const [grab, setGrab] = useState(false);

  const { main, single } = layout;
  const mainRef = useRef(main);
  mainRef.current = main;
  const viewports = useMemo(() => PLANES.map((plane) => ids[plane]), [ids]);
  const shownRef = useRef(shown);
  shownRef.current = shown;
  const painting = editable && (tool === "brush" || tool === "threshold" || tool === "eraser") && !grab;
  panning.current = tool === "pan" || grab;
  const windowing = useRef(false);
  windowing.current = !grab && (tool === "window" || (!editable && tool !== "pan"));

  useEffect(() => {
    const rendering = getEngine();
    const elements = { ...els.current } as Record<Plane, HTMLDivElement>;
    for (const plane of PLANES) {
      rendering.enableElement({
        viewportId: ids[plane],
        element: elements[plane],
        type: Enums.ViewportType.ORTHOGRAPHIC,
        defaultOptions: { orientation: ORIENTATION[plane], background: [0, 0, 0] as Types.Point3 },
      });
    }
    engine.current = rendering;

    const group = ToolGroupManager.createToolGroup(ids.tools)!;
    [PanTool, WindowLevelTool, ZoomTool, BrushTool].forEach((tool) => group.addTool(tool.toolName));
    group.addToolInstance(ERASER, BrushTool.toolName, { activeStrategy: "ERASE_INSIDE_CIRCLE" });
    // the threshold range is taken around the clicked point, so there is no range to set by hand
    group.addToolInstance(THRESHOLD, BrushTool.toolName, {
      activeStrategy: "THRESHOLD_INSIDE_CIRCLE",
      threshold: { isDynamic: true, dynamicRadius: 3 },
    });
    // the brush has its own keys (I, E, Enter, Esc) that clash with the app's shortcuts
    for (const name of [BrushTool.toolName, ERASER, THRESHOLD]) group.getToolInstance(name).configuration.actions = {};
    group.addTool(ReferenceLinesTool.toolName, { sourceViewportId: ids[mainRef.current] });
    for (const id of viewports) group.addViewport(id, ENGINE_ID);
    // pan and zoom work with any tool: middle button pans, right button zooms (Ctrl + wheel is handled below)
    group.setToolActive(PanTool.toolName, { bindings: [{ mouseButton: ToolEnums.MouseBindings.Auxiliary }] });
    group.setToolActive(ZoomTool.toolName, { bindings: [{ mouseButton: ToolEnums.MouseBindings.Secondary }] });
    group.setToolEnabled(ReferenceLinesTool.toolName);

    const resize = new ResizeObserver(() => rendering.resize(true, true));
    for (const plane of PLANES) resize.observe(elements[plane]);

    const onCamera = (event: Event) => {
      const { viewportId } = (event as CustomEvent<{ viewportId: string }>).detail;
      const plane = PLANES.find((p) => ids[p] === viewportId);
      if (!plane) return;
      const data = csUtils.getImageSliceDataForVolumeViewport(rendering.getViewport(viewportId) as Types.IVolumeViewport);
      if (data) setSlices((s) => ({ ...s, [plane]: { index: data.imageIndex, count: data.numberOfSlices } }));
      if (plane === mainRef.current) setZoom(zoomOf(plane));
    };
    for (const plane of PLANES) elements[plane].addEventListener(Enums.Events.CAMERA_MODIFIED, onCamera);

    const onVoi = (event: Event) => {
      const { viewportId, range } = (event as CustomEvent<{ viewportId: string; range: Types.VOIRange }>).detail;
      if (viewportId !== ids[mainRef.current] || !range) return;
      callbacks.current.onWindow?.({ width: range.upper - range.lower, center: (range.upper + range.lower) / 2 });
    };
    for (const plane of PLANES) elements[plane].addEventListener(Enums.Events.VOI_MODIFIED, onVoi);

    // a stroke counts as an edit only if it actually changed the labelmap
    const onModified = (event: Event) => {
      const { segmentationId } = (event as CustomEvent<{ segmentationId: string }>).detail;
      if (editing.current && segmentationId === ids.mask) editing.current.changed = true;
    };
    const onUp = () => {
      if (editing.current?.changed) callbacks.current.onEdit?.();
      editing.current = null;
    };
    eventTarget.addEventListener(ToolEnums.Events.SEGMENTATION_DATA_MODIFIED, onModified);
    window.addEventListener("pointerup", onUp);

    const planeOf = (target: EventTarget | null) => PLANES.find((plane) => elements[plane].contains(target as Node));

    // Shift + click points all planes at the same spot; it must not reach the brush
    const onMouseDown = (event: MouseEvent) => {
      const plane = planeOf(event.target);
      if (!plane) return;
      if (event.button === 1 || event.button === 2 || (event.button === 0 && panning.current && !event.shiftKey)) startZoom(plane);
      if (event.button === 0 && windowing.current && !event.shiftKey) setWindowChanged(true);
      if (!event.shiftKey || event.button !== 0) return;
      event.stopPropagation();
      event.preventDefault();
      const source = rendering.getViewport(ids[plane]) as Types.IVolumeViewport;
      const box = source.element.getBoundingClientRect();
      const world = source.canvasToWorld([event.clientX - box.left, event.clientY - box.top]);
      for (const other of PLANES) {
        if (other === plane) continue;
        const viewport = rendering.getViewport(ids[other]) as Types.IVolumeViewport;
        csUtils.jumpToSlice(viewport.element, { imageIndex: sliceOf(viewport, world).index });
      }
    };

    // the wheel scrolls slices one at a time; Ctrl + wheel (a trackpad pinch too) zooms towards the pointer
    let wheelTotal = 0;
    const onWheel = (event: WheelEvent) => {
      const plane = planeOf(event.target);
      if (!plane) return;
      event.stopPropagation();
      event.preventDefault();
      if (event.ctrlKey) {
        const viewport = rendering.getViewport(ids[plane]) as Types.IVolumeViewport;
        const box = viewport.element.getBoundingClientRect();
        const point: Types.Point2 = [event.clientX - box.left, event.clientY - box.top];
        const before = viewport.canvasToWorld(point);
        startZoom(plane);
        const lines = event.deltaMode === WheelEvent.DOM_DELTA_PIXEL ? event.deltaY : event.deltaY * 30;
        viewport.setZoom(viewport.getZoom() * Math.min(1.5, Math.max(0.67, Math.exp(-lines * 0.002))));
        const after = viewport.canvasToWorld(point);
        const { focalPoint, position } = viewport.getCamera();
        const shift = [0, 1, 2].map((a) => before[a] - after[a]);
        viewport.setCamera({
          focalPoint: focalPoint!.map((v, a) => v + shift[a]) as Types.Point3,
          position: position!.map((v, a) => v + shift[a]) as Types.Point3,
        });
        viewport.render();
        return;
      }
      wheelTotal += event.deltaMode === WheelEvent.DOM_DELTA_PIXEL ? event.deltaY : Math.sign(event.deltaY) * WHEEL_STEP;
      if (Math.abs(wheelTotal) < WHEEL_STEP) return;
      csUtils.scroll(rendering.getViewport(ids[plane]), { delta: Math.sign(wheelTotal) });
      wheelTotal = 0;
    };
    const root = rootEl.current!;
    root.addEventListener("mousedown", onMouseDown, true);
    root.addEventListener("wheel", onWheel, { capture: true, passive: false });

    return () => {
      for (const plane of PLANES) elements[plane].removeEventListener(Enums.Events.CAMERA_MODIFIED, onCamera);
      for (const plane of PLANES) elements[plane].removeEventListener(Enums.Events.VOI_MODIFIED, onVoi);
      eventTarget.removeEventListener(ToolEnums.Events.SEGMENTATION_DATA_MODIFIED, onModified);
      window.removeEventListener("pointerup", onUp);
      root.removeEventListener("mousedown", onMouseDown, true);
      root.removeEventListener("wheel", onWheel, true);
      resize.disconnect();
      ToolGroupManager.destroyToolGroup(ids.tools);
      for (const id of viewports) rendering.disableElement(id);
      engine.current = null;
    };
    // startZoom and zoomOf only read refs
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids, viewports]);

  // study + masks
  useEffect(() => {
    let cancelled = false;
    setProblem(null);
    setLoaded(false);
    setShown(null);
    setExtents({});
    if (!studyUid) {
      setProblem("no-study");
      return;
    }
    (async () => {
      const found = await findSeries(studyUid);
      if (cancelled) return;
      seriesUids.current = found;
      callbacks.current.onSeriesFound?.(Object.keys(found) as Series[]);
      // masks live on the main (post-contrast) series grid
      const main = await loadVolume(studyUid, found.post!);
      if (cancelled || !main) return;
      addMask(ids.mask, main, mask);
      original.current = (cache.getVolume(ids.mask)!.voxelManager!.getCompleteScalarDataArray!() as Uint8Array).slice();
      if (modelMask) addMask(ids.model, main, modelMask);
      setLoaded(true);
    })().catch((error) => !cancelled && setProblem(error instanceof DicomWebError ? error.kind : "unavailable"));

    return () => {
      cancelled = true;
      removeMask(ids.mask);
      removeMask(ids.model);
    };
  }, [ids, studyUid, mask, modelMask, attempt]);

  // series on screen; keeps the slice and zoom when switching
  useEffect(() => {
    const rendering = engine.current;
    if (!loaded || !studyUid || !rendering) return;
    let cancelled = false;
    const seriesUid = seriesUids.current[series] ?? seriesUids.current.post!;
    const cameras = shownRef.current ? viewports.map((id) => rendering.getViewport(id).getCamera()) : null;

    (async () => {
      const volume = await loadVolume(studyUid, seriesUid);
      if (cancelled || !volume) return;
      await setVolumesForViewports(rendering, [{ volumeId: volume.volumeId }], viewports);
      if (cancelled) return;
      for (const id of viewports) {
        const masks = modelMask ? [ids.mask, ids.model] : [ids.mask];
        for (const segmentationId of masks) {
          if (!segmentation.state.getSegmentationRepresentations(id, { segmentationId }).length) {
            segmentation.addLabelmapRepresentationToViewport(id, [{ segmentationId }]);
          }
        }
        segmentation.activeSegmentation.setActiveSegmentation(id, ids.mask);
      }
      callbacks.current.onGridMatch?.(sameGrid(volume, cache.getVolume(ids.mask)!));
      // the masks were painted before they had an actor, so push them to the GPU now
      segmentation.triggerSegmentationEvents.triggerSegmentationDataModified(ids.mask);
      if (modelMask) segmentation.triggerSegmentationEvents.triggerSegmentationDataModified(ids.model);

      if (cameras) {
        viewports.forEach((id, i) => rendering.getViewport(id).setCamera(cameras[i]));
      } else {
        for (const plane of PLANES) (rendering.getViewport(ids[plane]) as Types.IVolumeViewport).setOrientation(ALIGNED[plane], false, true);
      }
      if (!cameras && mask) {
        // open every plane on the lesion
        const center = maskCenterWorld(cache.getVolume(ids.mask)!, mask);
        for (const plane of PLANES) {
          const viewport = rendering.getViewport(ids[plane]) as Types.IVolumeViewport;
          await csUtils.jumpToSlice(viewport.element, { imageIndex: sliceOf(viewport, center).index });
        }
      }
      rendering.render();
      setWindowChanged(false);
      setShown(series);
    })().catch((error) => !cancelled && setProblem(error instanceof DicomWebError ? error.kind : "unavailable"));

    return () => {
      cancelled = true;
    };
  }, [ids, viewports, loaded, series, studyUid, mask, modelMask]);

  // proposal and corrections in pink, a confirmed model mask in light grey
  useEffect(() => {
    if (!shown || !segmentation.state.getSegmentation(ids.mask)) return;
    for (const id of viewports) {
      segmentation.config.visibility.setSegmentationRepresentationVisibility(id, { segmentationId: ids.mask, type: Labelmap }, showMask);
      segmentation.config.color.setSegmentIndexColor(id, ids.mask, 1, maskState === "confirmed" ? LIGHT : PINK);
      segmentation.config.style.setRenderInactiveSegmentations(id, true);
      if (modelMask) {
        segmentation.config.visibility.setSegmentationRepresentationVisibility(id, { segmentationId: ids.model, type: Labelmap }, showMask && modelOutline);
        segmentation.config.color.setSegmentIndexColor(id, ids.model, 1, PINK);
      }
    }
    // the model's proposal is an outline only; filled once corrected
    const fill = maskState === "corrected" ? 0.3 : maskState === "proposed" ? 0 : 0.15;
    segmentation.config.style.setStyle(
      { type: Labelmap, segmentationId: ids.mask },
      { renderOutline: true, outlineWidth: 1.5, outlineWidthInactive: 1.5, fillAlpha: fill, fillAlphaInactive: fill },
    );
    if (modelMask) {
      segmentation.config.style.setStyle(
        { type: Labelmap, segmentationId: ids.model },
        { renderFill: false, renderFillInactive: false, outlineWidth: 2, outlineWidthInactive: 2 },
      );
    }
    engine.current?.render();
  }, [ids, viewports, modelMask, shown, maskState, showMask, modelOutline]);

  // Space held down turns any tool into the hand for a moment
  useEffect(() => {
    const group = ToolGroupManager.getToolGroup(ids.tools);
    if (!group) return;
    const names: Record<Tool, string> = {
      brush: BrushTool.toolName,
      threshold: THRESHOLD,
      eraser: ERASER,
      pan: PanTool.toolName,
      window: WindowLevelTool.toolName,
    };
    const primary = grab ? PanTool.toolName : names[editable || tool === "pan" ? tool : "window"];
    for (const name of Object.values(names)) if (name !== primary) group.setToolPassive(name);
    group.setToolActive(primary, { bindings: [{ mouseButton: ToolEnums.MouseBindings.Primary }] });
  }, [ids, tool, editable, grab]);

  useEffect(() => {
    const group = ToolGroupManager.getToolGroup(ids.tools);
    if (!group) return;
    group.setToolConfiguration(BrushTool.toolName, { activeStrategy: STRATEGY[brushShape].brush });
    group.setToolConfiguration(THRESHOLD, { activeStrategy: STRATEGY[brushShape].threshold });
    group.setToolConfiguration(ERASER, { activeStrategy: STRATEGY[brushShape].eraser });
    toolUtils.segmentation.setBrushSizeForToolGroup(ids.tools, brushRadius);
  }, [ids, brushShape, brushRadius]);

  // where the mask is in every plane and which slices were changed, recounted after every change to it
  useEffect(() => {
    if (!shown) return;
    let timer = 0;
    const update = () => {
      const labelmap = cache.getVolume(ids.mask);
      if (!labelmap) return;
      const next: Partial<Record<Plane, Extent>> = {};
      for (const plane of PLANES) {
        const viewport = engine.current?.getViewport(ids[plane]) as Types.IVolumeViewport | undefined;
        if (!viewport) continue;
        // only the main plane shows edits, the others need no comparison
        const compare = plane === main ? original.current : null;
        next[plane] = maskExtent(labelmap, viewport.getCamera().viewPlaneNormal!, (world) => sliceOf(viewport, world).index, compare);
      }
      setExtents(next);
    };
    const onModified = (event: Event) => {
      if ((event as CustomEvent<{ segmentationId: string }>).detail.segmentationId !== ids.mask) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(update, 200);
    };
    update();
    eventTarget.addEventListener(ToolEnums.Events.SEGMENTATION_DATA_MODIFIED, onModified);
    return () => {
      window.clearTimeout(timer);
      eventTarget.removeEventListener(ToolEnums.Events.SEGMENTATION_DATA_MODIFIED, onModified);
    };
  }, [ids, main, shown]);

  // reference lines show where the main plane cuts the others
  useEffect(() => {
    const group = ToolGroupManager.getToolGroup(ids.tools);
    if (!group) return;
    group.setToolConfiguration(ReferenceLinesTool.toolName, { sourceViewportId: ids[main] });
    if (single) group.setToolDisabled(ReferenceLinesTool.toolName);
    else group.setToolEnabled(ReferenceLinesTool.toolName);
    setZoom(zoomOf(main));
    engine.current?.render();
    // zoomOf only reads refs
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids, main, single, shown]);

  // the grid changes size when the layout does, so the canvases follow on the next frame
  useEffect(() => {
    const frame = requestAnimationFrame(() => engine.current?.resize(true, true));
    return () => cancelAnimationFrame(frame);
  }, [main, single]);

  useEffect(() => {
    const viewportOf = (plane: Plane) => engine.current?.getViewport(ids[plane]);
    const onKey = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement).matches("input, select, textarea")) return;
      // only over the images, so Space still presses a focused button elsewhere
      if (event.key === " " && hovered.current) {
        event.preventDefault();
        if (!event.repeat) setGrab(true);
        return;
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const plane = hovered.current ?? mainRef.current;
      if (event.key === "ArrowUp" || event.key === "ArrowDown") {
        const viewport = viewportOf(plane);
        if (!viewport) return;
        event.preventDefault();
        csUtils.scroll(viewport, { delta: event.key === "ArrowDown" ? 1 : -1 });
      } else if (event.key === "1" || event.key === "2" || event.key === "3") {
        setLayout((l) => ({ ...l, main: PLANES[Number(event.key) - 1] }));
      } else if (event.key === "v") {
        setLayout((l) => ({ ...l, single: !l.single }));
      } else if (event.key === "+" || event.key === "=" || event.key === "-") {
        const viewport = viewportOf(mainRef.current);
        if (!viewport) return;
        startZoom(mainRef.current);
        viewport.setZoom(viewport.getZoom() * (event.key === "-" ? 0.8 : 1.25));
        viewport.render();
      } else if (event.key === "0") {
        fit();
      }
    };
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.key === " ") setGrab(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("keyup", onKeyUp);
    };
    // fit only reads refs
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids]);

  useImperativeHandle(
    ref,
    () => ({
      undo: () => historyMemo.undo(),
      restoreModel: () => {
        const labelmap = cache.getVolume(ids.mask);
        if (!labelmap || !mask) return;
        paintMask(labelmap, mask);
        segmentation.triggerSegmentationEvents.triggerSegmentationDataModified(ids.mask);
      },
      resetWindow,
      interpolate: async () => {
        const labelmap = cache.getVolume(ids.mask);
        if (!labelmap) return false;
        const voxels = labelmap.voxelManager!;
        const before = (voxels.getCompleteScalarDataArray!() as Uint8Array).slice();
        const viewport = engine.current?.getViewport(ids[mainRef.current]) as Types.IVolumeViewport | undefined;
        if (!viewport) return false;
        // let the button show that it is working before the main thread gets busy
        await new Promise(requestAnimationFrame);
        const after = interpolateMask(labelmap, viewport.getCamera().viewPlaneNormal!);
        if (!after) return false;
        const show = (data: ArrayLike<number>) => {
          voxels.setCompleteScalarDataArray!(data);
          segmentation.triggerSegmentationEvents.triggerSegmentationDataModified(ids.mask);
        };
        show(after);
        // one undo takes the whole fill back
        historyMemo.push({ restoreMemo: (undo) => show(undo ? before : after) });
        callbacks.current.onEdit?.();
        return true;
      },
      restoreSlice: () => {
        const labelmap = cache.getVolume(ids.mask);
        const viewport = engine.current?.getViewport(ids[mainRef.current]) as Types.IVolumeViewport | undefined;
        if (!labelmap || !viewport || !original.current) return false;
        const current = csUtils.getImageSliceDataForVolumeViewport(viewport)!.imageIndex;
        const redo = restoreSlice(labelmap, original.current, (world) => sliceOf(viewport, world).index, current);
        if (!redo) return false;
        segmentation.triggerSegmentationEvents.triggerSegmentationDataModified(ids.mask);
        historyMemo.push({
          restoreMemo: (undo) => {
            redo(!!undo);
            segmentation.triggerSegmentationEvents.triggerSegmentationDataModified(ids.mask);
          },
        });
        callbacks.current.onEdit?.();
        return true;
      },
      goToSlice: (index) => jump(index),
    }),
    // resetWindow only reads refs and stable ids
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ids, mask, viewports],
  );

  function resetWindow() {
    for (const id of viewports) (engine.current?.getViewport(id) as Types.IVolumeViewport | undefined)?.resetProperties();
    engine.current?.render();
    setWindowChanged(false);
  }

  function startZoom(plane: Plane) {
    const viewport = engine.current?.getViewport(ids[plane]);
    if (viewport && fitScale.current[plane] === undefined) fitScale.current[plane] = viewport.getCamera().parallelScale;
  }

  function zoomOf(plane: Plane) {
    const base = fitScale.current[plane];
    const scale = engine.current?.getViewport(ids[plane]).getCamera().parallelScale;
    return base && scale ? base / scale : null;
  }

  function fit() {
    const plane = mainRef.current;
    const viewport = engine.current?.getViewport(ids[plane]);
    if (!viewport) return;
    delete fitScale.current[plane];
    // back to the whole image, on the same slice
    viewport.resetCamera({ resetPan: true, resetZoom: true, resetToCenter: false });
    viewport.render();
    setZoom(null);
  }

  const mainExtent = extents[main];
  const currentEdited = !!mainExtent?.edited.includes(slices[main].index);
  useEffect(() => {
    if (!mainExtent) return;
    callbacks.current.onMaskInfo?.({
      slices: mainExtent.slices.length,
      gaps: mainExtent.gaps,
      edited: mainExtent.edited.length,
      currentEdited,
      sizeMm: mainExtent.sizeMm,
    });
  }, [mainExtent, currentEdited]);

  const jumpIn = (plane: Plane, imageIndex: number) => {
    const element = els.current[plane];
    if (element) csUtils.jumpToSlice(element, { imageIndex });
  };
  const jump = (imageIndex: number) => jumpIn(main, imageIndex);
  const makeMain = (plane: Plane) => setLayout((l) => ({ ...l, main: plane }));
  // fixed order in the side column: axial, sagittal, coronal without the main one
  const area = (plane: Plane) => (plane === main ? "main" : PLANES.filter((p) => p !== main).indexOf(plane) === 0 ? "first" : "second");
  const sets = useMemo(
    () =>
      Object.fromEntries(
        PLANES.map((plane) => {
          const extent = extents[plane];
          return [plane, { mask: new Set(extent?.slices), gaps: new Set(plane === main ? extent?.gaps : []), edited: new Set(extent?.edited) }];
        }),
      ) as Record<Plane, { mask: Set<number>; gaps: Set<number>; edited: Set<number> }>,
    [extents, main],
  );

  return (
    <div
      ref={rootEl}
      className={single ? "viewer viewer--single" : "viewer"}
      // the brush paints in every view, so a stroke anywhere can change the mask
      onPointerDownCapture={() => {
        if (painting) editing.current = { changed: false };
      }}
      onContextMenu={(event) => event.preventDefault()}
    >
      {PLANES.map((plane, i) => {
        const isMain = plane === main;
        return (
          <section
            key={plane}
            className={isMain ? "viewer__well viewer__well--main" : "viewer__well"}
            style={{ gridArea: area(plane) }}
            aria-label={t(`viewer.planeLabel.${plane}`)}
            onPointerEnter={() => (hovered.current = plane)}
            onPointerLeave={() => (hovered.current = null)}
          >
            <header className="viewer__head">
              <b>{`${i + 1} · ${t(`viewer.plane.${plane}`)}`}</b>
              {slices[plane].count > 0 && (
                <span className="viewer__pos">
                  {t("viewer.position", { n: slices[plane].index + 1 })} <span>{t("viewer.positionOf", { n: slices[plane].count })}</span>
                </span>
              )}
              <span className="viewer__head-end">
                {isMain && zoom !== null && (
                  <>
                    <span>{t("viewer.zoom", { n: formatOneDecimal(zoom) })}</span>
                    <button type="button" className="viewer__head-btn" title={t("viewer.fitTitle")} onClick={fit}>
                      {t("viewer.fit")}
                    </button>
                  </>
                )}
                {isMain && windowChanged && (
                  <button type="button" className="viewer__head-btn" title={t("viewer.windowRestoreTitle")} onClick={resetWindow}>
                    {t("viewer.windowRestore")}
                  </button>
                )}
                {!isMain && (
                  <button type="button" className="viewer__head-btn" title={t("viewer.makeMain", { key: i + 1 })} onClick={() => makeMain(plane)}>
                    <svg viewBox="0 0 16 16" aria-hidden="true">
                      <path d="M9.5 2.5h4v4 M13.5 2.5L9 7 M6.5 13.5h-4v-4 M2.5 13.5L7 9" />
                    </svg>
                    {i + 1}
                  </button>
                )}
              </span>
            </header>
            <div
              className="viewer__image"
              // double click swaps planes, or brings the study's contrast back while adjusting it;
              // skipped while painting, where it would also lay two brush dots
              onDoubleClick={() => {
                if (painting) return;
                if (windowing.current) return resetWindow();
                if (isMain) setLayout((l) => ({ ...l, single: !l.single }));
                else makeMain(plane);
              }}
            >
              {shown && (
                <SliceStrip
                  count={slices[plane].count}
                  current={slices[plane].index}
                  mask={sets[plane].mask}
                  gaps={sets[plane].gaps}
                  edited={sets[plane].edited}
                  big={isMain}
                  onPick={(index) => jumpIn(plane, index)}
                />
              )}
              <div
                ref={(element) => (els.current[plane] = element)}
                className={painting ? "viewer__canvas viewer__canvas--paint" : "viewer__canvas"}
                role="img"
                aria-label={t(`viewer.planeLabel.${plane}`)}
              />
              <span className="viewer__edge viewer__edge--start">{t(`viewer.edge.${plane}.start`)}</span>
              <span className="viewer__edge viewer__edge--end">{t(`viewer.edge.${plane}.end`)}</span>
            </div>
          </section>
        );
      })}

      {(!shown || problem) && (
        <div className="viewer__status" role={problem ? "alert" : "status"}>
          {problem ? (
            <>
              <b>{t(`viewer.problem.${problem}`)}</b>
              {problem !== "no-study" && (
                <button type="button" className="btn" onClick={() => setAttempt((n) => n + 1)}>
                  {t("state.retry")}
                </button>
              )}
            </>
          ) : (
            t("viewer.loading")
          )}
        </div>
      )}
    </div>
  );
});

export default Viewer;
