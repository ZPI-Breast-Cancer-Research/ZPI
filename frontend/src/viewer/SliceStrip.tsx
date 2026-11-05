import { useEffect, useRef, useState } from "react";

import { t } from "../i18n";

interface Props {
  count: number;
  current: number;
  mask: Set<number>;
  gaps: Set<number>;
  edited: Set<number>;
  // the main view gets wide marks and the number of the slice on screen
  big: boolean;
  onPick: (index: number) => void;
}

const TOP = 12;
const PINK = "#ec6f98";
const WARN = "#f0907f";
const INK = "#e8ecf1";
const EMPTY = "rgba(196, 200, 206, 0.3)";

function mark(x: number, y: number, w: number, h: number, fill: string, stroke: string, dashed = false) {
  const s = h * 1.1;
  return <path d={`M${x + s} ${y} h${w} l${-s} ${h} h${-w} z`} fill={fill} stroke={stroke} strokeWidth={1.2} strokeDasharray={dashed ? "2 2" : undefined} />;
}

// one slanted mark per slice when they fit, else one per few; a shared mark shows the most important of its slices
export default function SliceStrip({ count, current, mask, gaps, edited, big, onPick }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(0);

  useEffect(() => {
    const element = box.current!;
    const observer = new ResizeObserver(() => setHeight(element.clientHeight));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const bins = Math.max(2, Math.min(count, Math.floor((height - 2 * TOP) / (big ? 9 : 12))));
  const per = count / bins;
  const step = (height - 2 * TOP) / (bins - 1);
  const binOf = (index: number) => Math.min(bins - 1, Math.floor(index / per));
  const [x, w, h] = big ? [8, 20, 6] : [4, 9, 4];

  const pick = (clientY: number) => {
    const top = box.current!.getBoundingClientRect().top;
    const bin = Math.max(0, Math.min(bins - 1, Math.round((clientY - top - TOP) / step)));
    onPick(Math.min(count - 1, Math.floor(bin * per + per / 2)));
  };

  const marks = [];
  if (count > 0 && height > 0) {
    const currentBin = binOf(current);
    for (let bin = 0; bin < bins; bin++) {
      const from = Math.floor(bin * per);
      const to = Math.max(from, Math.floor((bin + 1) * per) - 1);
      const has = (set: Set<number>) => {
        for (let i = from; i <= to; i++) if (set.has(i)) return true;
        return false;
      };
      const y = TOP + bin * step - h / 2;
      marks.push(
        <g key={bin}>
          {bin === currentBin
            ? mark(x - 4, y - 1, w + 10, h + 1, INK, INK)
            : has(gaps)
              ? mark(x, y, w, h, "none", WARN, true)
              : has(edited)
                ? mark(x, y, w, h, PINK, PINK)
                : has(mask)
                  ? mark(x, y, w, h, "none", PINK)
                  : mark(x, y, w, h, "none", EMPTY)}
        </g>,
      );
    }
  }
  const labelY = TOP + binOf(current) * step;
  const label = String(current + 1);
  const labelWidth = label.length * 8 + 12;

  return (
    <div
      ref={box}
      className={big ? "slice-strip slice-strip--big" : "slice-strip"}
      role="slider"
      aria-label={t("viewer.slices")}
      aria-valuemin={1}
      aria-valuemax={count}
      aria-valuenow={current + 1}
      onPointerDown={(event) => {
        if (event.button !== 0 || !count) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        pick(event.clientY);
      }}
      onPointerMove={(event) => event.currentTarget.hasPointerCapture(event.pointerId) && pick(event.clientY)}
    >
      <svg width="100%" height="100%" aria-hidden="true">
        {marks}
        {big && count > 0 && height > 0 && (
          <g>
            <rect x={36} y={labelY - 10} width={labelWidth} height={19} rx={2} fill={INK} />
            <text x={36 + labelWidth / 2} y={labelY + 4.5} textAnchor="middle" className="slice-strip__number">
              {label}
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}
