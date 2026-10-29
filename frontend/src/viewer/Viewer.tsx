import { cache, Enums, eventTarget, setVolumesForViewports, utilities as csUtils, volumeLoader, type Types } from "@cornerstonejs/core";
import {
  BrushTool,
  Enums as ToolEnums,
  PanTool,
  ReferenceLinesTool,
  segmentation,
  StackScrollTool,
  ToolGroupManager,
  utilities as toolUtils,
  WindowLevelTool,
  ZoomTool,
} from "@cornerstonejs/tools";
import { forwardRef, useEffect, useId, useImperativeHandle, useMemo, useRef, useState } from "react";

import { t } from "../i18n";
import { ENGINE_ID, getEngine, historyMemo, maskCenterWorld, paintMask } from "./cornerstone";
import { DicomWebError, findSeries, seriesImageIds } from "./dicomweb";
import type { MaskSource, MaskState, Series, Tool } from "./types";
import "./viewer.css";

const PLANES = 32;
const ERASER = "Eraser";
const Labelmap = ToolEnums.SegmentationRepresentations.Labelmap;
const PINK: Types.Color = [236, 111, 152, 255];
const LIGHT: Types.Color = [232, 236, 241, 255];

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
  onEdit?: () => void;
  onSeriesFound?: (available: Series[]) => void;
}

export interface ViewerHandle {
  undo: () => void;
  restoreModel: () => void;
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
  { studyUid, mask, modelMask = null, series, maskState, showMask, tool = "window", editable = false, modelOutline = false, onEdit, onSeriesFound },
  ref,
) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const ids = useMemo(
    () => ({ axial: `axial-${uid}`, sagittal: `sagittal-${uid}`, tools: `tools-${uid}`, mask: `mask-${uid}`, model: `model-${uid}` }),
    [uid],
  );
  const axialEl = useRef<HTMLDivElement>(null);
  const sagittalEl = useRef<HTMLDivElement>(null);
  const engine = useRef<ReturnType<typeof getEngine> | null>(null);
  const seriesUids = useRef<Partial<Record<Series, string>>>({});
  const editing = useRef<{ changed: boolean } | null>(null);
  const callbacks = useRef({ onEdit, onSeriesFound });
  callbacks.current = { onEdit, onSeriesFound };

  const [problem, setProblem] = useState<Problem | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [shown, setShown] = useState<Series | null>(null);
  const [slice, setSlice] = useState({ index: 0, count: 0 });
  const [lesion, setLesion] = useState<[number, number] | null>(null);

  const viewports = useMemo(() => [ids.axial, ids.sagittal], [ids]);
  const shownRef = useRef(shown);
  shownRef.current = shown;
  const painting = editable && (tool === "brush" || tool === "eraser");

  useEffect(() => {
    const rendering = getEngine();
    const options = (orientation: Enums.OrientationAxis) => ({ orientation, background: [0, 0, 0] as Types.Point3 });
    rendering.enableElement({ viewportId: ids.axial, element: axialEl.current!, type: Enums.ViewportType.ORTHOGRAPHIC, defaultOptions: options(Enums.OrientationAxis.AXIAL) });
    rendering.enableElement({ viewportId: ids.sagittal, element: sagittalEl.current!, type: Enums.ViewportType.ORTHOGRAPHIC, defaultOptions: options(Enums.OrientationAxis.SAGITTAL) });
    engine.current = rendering;

    const group = ToolGroupManager.createToolGroup(ids.tools)!;
    [PanTool, WindowLevelTool, StackScrollTool, ZoomTool, BrushTool].forEach((tool) => group.addTool(tool.toolName));
    group.addToolInstance(ERASER, BrushTool.toolName, { activeStrategy: "ERASE_INSIDE_CIRCLE" });
    group.addTool(ReferenceLinesTool.toolName, { sourceViewportId: ids.axial });
    group.addViewport(ids.axial, ENGINE_ID);
    group.addViewport(ids.sagittal, ENGINE_ID);
    group.setToolActive(StackScrollTool.toolName, { bindings: [{ mouseButton: ToolEnums.MouseBindings.Wheel }] });
    group.setToolActive(ZoomTool.toolName, { bindings: [{ mouseButton: ToolEnums.MouseBindings.Secondary }] });
    group.setToolEnabled(ReferenceLinesTool.toolName);
    toolUtils.segmentation.setBrushSizeForToolGroup(ids.tools, 5);

    const resize = new ResizeObserver(() => rendering.resize(true, true));
    resize.observe(axialEl.current!);
    resize.observe(sagittalEl.current!);

    const axial = axialEl.current!;
    const onCamera = () => {
      const data = csUtils.getImageSliceDataForVolumeViewport(rendering.getViewport(ids.axial) as Types.IVolumeViewport);
      if (data) setSlice({ index: data.imageIndex, count: data.numberOfSlices });
    };
    axial.addEventListener(Enums.Events.CAMERA_MODIFIED, onCamera);

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

    return () => {
      axial.removeEventListener(Enums.Events.CAMERA_MODIFIED, onCamera);
      eventTarget.removeEventListener(ToolEnums.Events.SEGMENTATION_DATA_MODIFIED, onModified);
      window.removeEventListener("pointerup", onUp);
      resize.disconnect();
      ToolGroupManager.destroyToolGroup(ids.tools);
      rendering.disableElement(ids.axial);
      rendering.disableElement(ids.sagittal);
      engine.current = null;
    };
  }, [ids]);

  // study + masks
  useEffect(() => {
    let cancelled = false;
    setProblem(null);
    setLoaded(false);
    setShown(null);
    setLesion(null);
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
      // the masks were painted before they had an actor, so push them to the GPU now
      segmentation.triggerSegmentationEvents.triggerSegmentationDataModified(ids.mask);
      if (modelMask) segmentation.triggerSegmentationEvents.triggerSegmentationDataModified(ids.model);

      if (cameras) {
        viewports.forEach((id, i) => rendering.getViewport(id).setCamera(cameras[i]));
      } else if (mask) {
        const center = maskCenterWorld(cache.getVolume(ids.mask)!, mask);
        const axial = rendering.getViewport(ids.axial) as Types.IVolumeViewport;
        const at = sliceOf(axial, center);
        const half = Math.round(mask.radius[2] / at.spacing);
        setLesion([at.index - half, at.index + half]);
        await csUtils.jumpToSlice(axial.element, { imageIndex: at.index });
        const sagittal = rendering.getViewport(ids.sagittal) as Types.IVolumeViewport;
        await csUtils.jumpToSlice(sagittal.element, { imageIndex: sliceOf(sagittal, center).index });
      }
      rendering.render();
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
    const fill = maskState === "corrected" ? 0.3 : 0.15;
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

  useEffect(() => {
    const group = ToolGroupManager.getToolGroup(ids.tools);
    if (!group) return;
    const names: Record<Tool, string> = { brush: BrushTool.toolName, eraser: ERASER, pan: PanTool.toolName, window: WindowLevelTool.toolName };
    const primary = names[editable || tool === "pan" ? tool : "window"];
    for (const name of Object.values(names)) if (name !== primary) group.setToolPassive(name);
    group.setToolActive(primary, { bindings: [{ mouseButton: ToolEnums.MouseBindings.Primary }] });
  }, [ids, tool, editable]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement).matches("input, select, textarea")) return;
      const delta = event.key === "ArrowUp" ? -1 : event.key === "ArrowDown" ? 1 : 0;
      const viewport = engine.current?.getViewport(ids.axial);
      if (!delta || !viewport) return;
      event.preventDefault();
      csUtils.scroll(viewport, { delta });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
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
    }),
    [ids, mask],
  );

  const jump = (imageIndex: number) => axialEl.current && csUtils.jumpToSlice(axialEl.current, { imageIndex });
  const seriesName = t(`viewer.series.${shown ?? series}`);
  const maskNote = maskState === "corrected" ? t("viewer.mask.corrected") : maskState === "confirmed" ? t("viewer.mask.confirmed") : t("viewer.mask.proposed");
  const perPlane = slice.count / PLANES;

  return (
    <div className="viewer">
      <div className="viewer__planes" aria-label={t("viewer.slices")}>
        {slice.count > 0 &&
          Array.from({ length: PLANES }, (_, i) => {
            const from = Math.floor(i * perPlane);
            const to = Math.max(from, Math.floor((i + 1) * perPlane) - 1);
            const hasLesion = lesion !== null && to >= lesion[0] && from <= lesion[1];
            const current = slice.index >= from && slice.index <= to;
            return (
              <button
                key={i}
                type="button"
                className={`viewer__plane${hasLesion ? " viewer__plane--lesion" : ""}${current ? " viewer__plane--current" : ""}`}
                style={{ top: `calc(${(i / PLANES) * 100}% + 4px)` }}
                aria-label={`${t("viewer.slices")} ${from + 1}–${to + 1}`}
                onClick={() => jump(Math.round((from + to) / 2))}
              />
            );
          })}
      </div>

      <div
        className="viewer__well"
        onContextMenu={(event) => event.preventDefault()}
        onPointerDownCapture={() => {
          if (painting) editing.current = { changed: false };
        }}
      >
        <div ref={axialEl} className={painting ? "viewer__canvas viewer__canvas--paint" : "viewer__canvas"} role="img" aria-label={t("viewer.axialLabel")} />
        {shown && (
          <>
            <div className="viewer__dc viewer__dc--tl">
              {t("viewer.axial")} · {seriesName}
              <br />
              {t("viewer.imageNo")} {slice.index + 1}/{slice.count}
            </div>
            <div className="viewer__dc viewer__dc--tr">P &nbsp; ← → &nbsp; L</div>
            <div className="viewer__dc viewer__dc--bl">
              <span className="viewer__mask-note">{maskNote}</span>
              {modelOutline && <span className="viewer__mask-note"> · {t("viewer.mask.model")}</span>}
            </div>
          </>
        )}
      </div>

      <div className="viewer__well viewer__well--side" onContextMenu={(event) => event.preventDefault()}>
        <div ref={sagittalEl} className="viewer__canvas" role="img" aria-label={t("viewer.sagittalLabel")} />
        {shown && (
          <>
            <div className="viewer__dc viewer__dc--tl">{t("viewer.sagittal")}</div>
            <div className="viewer__dc viewer__dc--bl">
              {t("viewer.line")} {slice.index + 1}
            </div>
          </>
        )}
      </div>

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
