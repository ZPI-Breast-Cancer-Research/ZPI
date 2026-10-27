import Panel from "../components/layout/Panel";
import { formatDayMonth } from "../format";
import { t } from "../i18n";
import type { VerifiedDay } from "./api";

const UNCHANGED = "#5b6b85";
const CORRECTED = "#c9628a";
const WIDTH = 420;
const HEIGHT = 110;

export default function VerifiedChart({ days }: { days: VerifiedDay[] }) {
  const max = Math.max(1, ...days.map((d) => d.unchanged + d.corrected));
  const slot = WIDTH / days.length;
  const barWidth = slot * 0.5;

  return (
    <Panel title={t("dashboard.verified")} aux={t("dashboard.verified.period")}>
      <div className="chart">
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT + 2}`} preserveAspectRatio="none" role="img" aria-label={t("dashboard.verified.chart")}>
          {[0, 1, 2].map((k) => (
            <line key={k} x1="0" x2={WIDTH} y1={(HEIGHT * k) / 3} y2={(HEIGHT * k) / 3} stroke="#22314b" />
          ))}
          {days.map((day, i) => {
            const x = i * slot + (slot - barWidth) / 2;
            const unchanged = (day.unchanged / max) * HEIGHT * 0.9;
            const corrected = (day.corrected / max) * HEIGHT * 0.9;
            return (
              <g key={day.date}>
                <title>{`${formatDayMonth(day.date)}: ${day.unchanged} ${t("dashboard.verified.unchanged")}, ${day.corrected} ${t("dashboard.verified.corrected")}`}</title>
                <rect x={x} y={HEIGHT - unchanged - corrected} width={barWidth} height={corrected} fill={CORRECTED} />
                <rect x={x} y={HEIGHT - unchanged} width={barWidth} height={unchanged} fill={UNCHANGED} />
              </g>
            );
          })}
          <line x1="0" x2={WIDTH} y1={HEIGHT} y2={HEIGHT} stroke="#34465f" />
        </svg>
      </div>
      <div className="chart__axis">
        {days.map((day) => (
          <span key={day.date}>{formatDayMonth(day.date)}</span>
        ))}
      </div>
      <div className="chart__legend">
        <span>
          <i style={{ background: UNCHANGED }} />
          {t("dashboard.verified.unchanged")}
        </span>
        <span>
          <i style={{ background: CORRECTED }} />
          {t("dashboard.verified.corrected")}
        </span>
      </div>
    </Panel>
  );
}
