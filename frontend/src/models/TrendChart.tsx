import { formatDate, formatPercent } from "../format";
import { t } from "../i18n";

interface Point {
  week: string;
  share: number;
  versionChange?: string;
}

const W = 600;

export default function TrendChart({ points }: { points: Point[] }) {
  if (points.length < 2) return null;
  const max = Math.max(...points.map((p) => p.share)) * 1.25;
  const x = (i: number) => (i * W) / (points.length - 1);
  const y = (share: number) => 100 - (share / max) * 100;
  const change = points.findIndex((p) => p.versionChange);

  return (
    <div className="trend">
      <svg viewBox={`0 0 ${W} 100`} preserveAspectRatio="none" role="img" aria-label={t("models.weekly.chart")}>
        {[25, 50, 75].map((gy) => (
          <line key={gy} x1="0" x2={W} y1={gy} y2={gy} stroke="#1f2b42" />
        ))}
        <polyline
          points={points.map((p, i) => `${x(i)},${y(p.share)}`).join(" ")}
          fill="none"
          stroke="#8fa3c4"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
        {points.map((p, i) => (
          <circle key={p.week} cx={x(i)} cy={y(p.share)} r="8" fill="transparent">
            <title>{`${formatDate(p.week)}: ${formatPercent(p.share)}`}</title>
          </circle>
        ))}
        {change >= 0 && (
          <line x1={x(change)} x2={x(change)} y1="0" y2="100" stroke="#ec6f98" strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
        )}
      </svg>
      {change >= 0 && (
        <span className="trend__marker" style={{ left: `calc(${(change / (points.length - 1)) * 100}% + 6px)` }}>
          {t("models.version")} {points[change].versionChange}
        </span>
      )}
    </div>
  );
}
