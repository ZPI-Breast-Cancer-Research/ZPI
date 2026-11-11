const decimal = new Intl.NumberFormat("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function formatDecimal(value: number): string {
  return decimal.format(value);
}

// ISO date (YYYY-MM-DD) -> DD.MM.YYYY
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [year, month, day] = iso.split("-");
  return day && month && year ? `${day}.${month}.${year}` : iso;
}

// ISO date and time -> HH:MM today, DD.MM.YYYY, HH:MM otherwise
export function formatWhen(iso: string, today = new Date()): string {
  const [date, time = ""] = iso.split("T");
  const isToday = date === toIsoDate(today);
  return isToday ? time.slice(0, 5) : `${formatDate(date)}, ${time.slice(0, 5)}`;
}

export function toIsoDate(day: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}

export function formatDayMonth(iso: string): string {
  return formatDate(iso).slice(0, 5);
}

const plain = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 1 });

export function formatNumber(value: number): string {
  return plain.format(value);
}

const oneDecimal = new Intl.NumberFormat("pl-PL", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export function formatOneDecimal(value: number): string {
  return oneDecimal.format(value);
}

const percent = new Intl.NumberFormat("pl-PL", { style: "percent", maximumFractionDigits: 0 });

export function formatPercent(value: number | null | undefined): string {
  if (value == null) return "—";
  return percent.format(value);
}

// seconds -> m:ss
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function formatMetric(value: number | null, unit = ""): string {
  return value === null ? "—" : `${formatDecimal(value)}${unit}`;
}
