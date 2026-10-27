// TODO: replace with Cornerstone3D (DICOMweb via the gateway); this only draws labelled frames and a mask outline
const SIZE = 512;

export const CANVAS_SIZE = SIZE;

export function drawFrame(canvas: HTMLCanvasElement, title: string, subtitle: string) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.fillStyle = "#050608";
  ctx.fillRect(0, 0, SIZE, SIZE);
  ctx.strokeStyle = "rgba(196,200,206,.12)";
  ctx.lineWidth = 1;
  ctx.strokeRect(24.5, 24.5, 463, 463);
  ctx.beginPath();
  ctx.moveTo(24, 24);
  ctx.lineTo(488, 488);
  ctx.moveTo(488, 24);
  ctx.lineTo(24, 488);
  ctx.stroke();
  ctx.fillStyle = "#050608";
  ctx.fillRect(146, 226, 220, 62);
  ctx.textAlign = "center";
  ctx.fillStyle = "#9aa4b5";
  ctx.font = "600 17px 'Public Sans', sans-serif";
  ctx.fillText(title, 256, 252);
  ctx.fillStyle = "#6f7a8d";
  ctx.font = "400 14px 'Public Sans', sans-serif";
  ctx.fillText(subtitle, 256, 274);
  return ctx;
}

const radius = (t: number, scale: number) =>
  21 * scale * (1 + 0.22 * Math.sin(3 * t + 0.4) + 0.13 * Math.sin(7 * t + 1.1) + 0.08 * Math.sin(11 * t + 2));

export interface OutlineStyle {
  color: string;
  dashed: boolean;
  fill: number;
}

export function drawLesion(ctx: CanvasRenderingContext2D, x: number, y: number, scale: number, style: OutlineStyle) {
  if (scale <= 0.05) return;
  ctx.beginPath();
  for (let k = 0; k <= 96; k++) {
    const t = (k / 96) * Math.PI * 2;
    const r = radius(t + 0.15, scale) + 2 * Math.sin(5 * t);
    const px = x + Math.cos(t) * r;
    const py = y + Math.sin(t) * r;
    if (k === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();
  ctx.fillStyle = `rgba(236,111,152,${style.fill})`;
  ctx.fill();
  ctx.strokeStyle = style.color;
  ctx.lineWidth = 1.5;
  ctx.setLineDash(style.dashed ? [5, 4] : []);
  ctx.stroke();
  ctx.setLineDash([]);
}

// how big the lesion looks on a given slice: largest in the middle of its range, gone outside it
export function lesionScale(slice: number, [from, to]: [number, number]): number {
  if (slice < from || slice > to) return 0;
  const middle = (from + to) / 2;
  const d = (slice - middle) / ((to - from) / 3.2);
  return Math.exp(-d * d);
}
