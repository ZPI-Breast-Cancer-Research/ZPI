const decimal = new Intl.NumberFormat("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function formatDecimal(value: number): string {
  return decimal.format(value);
}

// ISO date (YYYY-MM-DD) -> DD.MM.YYYY
export function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return day && month && year ? `${day}.${month}.${year}` : iso;
}

export function formatDayMonth(iso: string): string {
  return formatDate(iso).slice(0, 5);
}

const oneDecimal = new Intl.NumberFormat("pl-PL", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export function formatOneDecimal(value: number): string {
  return oneDecimal.format(value);
}

const percent = new Intl.NumberFormat("pl-PL", { style: "percent", maximumFractionDigits: 0 });

export function formatPercent(share: number): string {
  return percent.format(share);
}

// seconds -> m:ss
export function formatDuration(seconds: number): string {
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function formatMetric(value: number | null, unit = ""): string {
  return value === null ? "—" : `${formatDecimal(value)}${unit}`;
}
