import { useEffect, useRef, useState } from "react";

import { t } from "../i18n";
import { CANVAS_SIZE, drawFrame, drawLesion, lesionScale } from "./placeholder";
import type { Lesion, MaskState, Series, Stroke, Tool } from "./types";
import "./viewer.css";

const SLICES = 96;
const PLANES = 32;

interface Props {
  lesion: Lesion;
  series: Series;
  mask: MaskState;
  strokes: Stroke[];
  showMask: boolean;
  tool?: Tool;
  editable?: boolean;
  modelOutline?: boolean;
  onStroke?: (stroke: Stroke) => void;
}

function useCanvasPoint(canvas: React.RefObject<HTMLCanvasElement>) {
  return (event: React.PointerEvent): [number, number] => {
    const rect = canvas.current!.getBoundingClientRect();
    const side = Math.min(rect.width, rect.height);
    return [
      ((event.clientX - rect.left - (rect.width - side) / 2) / side) * CANVAS_SIZE,
      ((event.clientY - rect.top - (rect.height - side) / 2) / side) * CANVAS_SIZE,
    ];
  };
}

export default function Viewer({ lesion, series, mask, strokes, showMask, tool = "brush", editable = false, modelOutline = false, onStroke }: Props) {
  const axial = useRef<HTMLCanvasElement>(null);
  const overlay = useRef<HTMLCanvasElement>(null);
  const sagittal = useRef<HTMLCanvasElement>(null);
  const [slice, setSlice] = useState(Math.round((lesion.slices[0] + lesion.slices[1]) / 2));
  const [drawing, setDrawing] = useState<Stroke | null>(null);
  const point = useCanvasPoint(overlay);
  const seriesName = t(`viewer.series.${series}`);

  useEffect(() => setSlice(Math.round((lesion.slices[0] + lesion.slices[1]) / 2)), [lesion]);

  useEffect(() => {
    if (axial.current) drawFrame(axial.current, t("viewer.image"), `${t("viewer.axial")} · ${seriesName}`);
    const ctx = sagittal.current && drawFrame(sagittal.current, t("viewer.reconstruction"), t("viewer.sagittal"));
    if (ctx) {
      const y = 40 + (slice / SLICES) * 432;
      ctx.strokeStyle = "rgba(236,111,152,.9)";
      ctx.lineWidth = 1.5;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(30, y);
      ctx.lineTo(482, y);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }, [slice, seriesName]);

  useEffect(() => {
    const ctx = overlay.current?.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);
    if (!showMask) return;
    const scale = lesionScale(slice, lesion.slices) * 1.08;
    if (modelOutline) drawLesion(ctx, lesion.x - 4, lesion.y - 4, scale * 0.9, { color: "#ec6f98", dashed: true, fill: 0 });
    drawLesion(ctx, lesion.x, lesion.y, scale, {
      color: mask === "proposed" ? "#ec6f98" : "#e8ecf1",
      dashed: mask === "proposed",
      fill: mask === "corrected" ? 0.22 : 0.08,
    });
    for (const stroke of drawing ? [...strokes, drawing] : strokes) {
      if (stroke.slice !== slice) continue;
      ctx.globalCompositeOperation = stroke.erase ? "destination-out" : "source-over";
      ctx.strokeStyle = "rgba(236,111,152,.55)";
      ctx.lineWidth = 10;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.beginPath();
      stroke.points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.stroke();
    }
    ctx.globalCompositeOperation = "source-over";
  }, [slice, lesion, mask, strokes, drawing, showMask, modelOutline]);

  const painting = editable && (tool === "brush" || tool === "eraser");
  const step = (delta: number) => setSlice((s) => Math.max(1, Math.min(SLICES, s + delta)));

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement).matches("input, select, textarea")) return;
      if (event.key === "ArrowUp") step(-1);
      else if (event.key === "ArrowDown") step(1);
      else return;
      event.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const maskNote = mask === "corrected" ? t("viewer.mask.corrected") : mask === "confirmed" ? t("viewer.mask.confirmed") : t("viewer.mask.proposed");

  return (
    <div className="viewer">
      <div className="viewer__planes" aria-label={t("viewer.slices")}>
        {Array.from({ length: PLANES }, (_, i) => {
          const from = i * 3 + 1;
          const to = from + 2;
          const hasLesion = to >= lesion.slices[0] && from <= lesion.slices[1];
          const current = slice >= from && slice <= to;
          return (
            <button
              key={i}
              type="button"
              className={`viewer__plane${hasLesion ? " viewer__plane--lesion" : ""}${current ? " viewer__plane--current" : ""}`}
              style={{ top: `calc(${(i / PLANES) * 100}% + 4px)` }}
              aria-label={`${t("viewer.slices")} ${from}–${to}`}
              onClick={() => setSlice(from + 1)}
            />
          );
        })}
      </div>

      <div className="viewer__well" onWheel={(event) => step(event.deltaY > 0 ? 1 : -1)}>
        <canvas ref={axial} width={CANVAS_SIZE} height={CANVAS_SIZE} role="img" aria-label={t("viewer.axialLabel")} />
        <canvas
          ref={overlay}
          width={CANVAS_SIZE}
          height={CANVAS_SIZE}
          className={painting ? "viewer__overlay viewer__overlay--paint" : "viewer__overlay"}
          onPointerDown={(event) => {
            if (!painting) return;
            event.currentTarget.setPointerCapture(event.pointerId);
            setDrawing({ slice, erase: tool === "eraser", points: [point(event)] });
          }}
          onPointerMove={(event) => drawing && setDrawing({ ...drawing, points: [...drawing.points, point(event)] })}
          onPointerUp={() => {
            if (drawing) onStroke?.(drawing);
            setDrawing(null);
          }}
        />
        <div className="viewer__dc viewer__dc--tl">
          {t("viewer.axial")} · {seriesName}
          <br />
          {t("viewer.imageNo")} {slice}/{SLICES}
        </div>
        <div className="viewer__dc viewer__dc--tr">P &nbsp; ← → &nbsp; L</div>
        <div className="viewer__dc viewer__dc--bl">
          <span className="viewer__mask-note">{maskNote}</span>
          {modelOutline && <span className="viewer__mask-note"> · {t("viewer.mask.model")}</span>}
        </div>
      </div>

      <div className="viewer__well viewer__well--side">
        <canvas ref={sagittal} width={CANVAS_SIZE} height={CANVAS_SIZE} role="img" aria-label={t("viewer.sagittalLabel")} />
        <div className="viewer__dc viewer__dc--tl">{t("viewer.sagittal")}</div>
        <div className="viewer__dc viewer__dc--bl">
          {t("viewer.line")} {slice}
        </div>
      </div>
    </div>
  );
}
