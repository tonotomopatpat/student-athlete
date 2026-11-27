const pad = (value: number) => String(value).padStart(2, "0");

/** The API stores campus-local wall-clock time without an offset; these helpers keep it that way. */
export function toNaiveIso(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:00`;
}

export function toDateInput(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function parseNaive(value: string): Date {
  return new Date(value);
}

export function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

export function formatTime(value: string | Date): string {
  const date = typeof value === "string" ? parseNaive(value) : value;
  return date.toLocaleTimeString("en-PH", { hour: "numeric", minute: "2-digit", hour12: true });
}

export function formatTimeRange(start: string, end: string): string {
  return `${formatTime(start)} – ${formatTime(end)}`;
}

export function formatDay(value: string | Date, style: "long" | "short" = "long"): string {
  const date = typeof value === "string" ? parseNaive(value) : value;
  return date.toLocaleDateString("en-PH", {
    weekday: style === "long" ? "long" : "short",
    month: style === "long" ? "long" : "short",
    day: "numeric",
  });
}

export function formatDateTime(value: string): string {
  return `${formatDay(value, "short")}, ${formatTime(value)}`;
}

export function dayKey(value: string | Date): string {
  const date = typeof value === "string" ? parseNaive(value) : value;
  return toDateInput(date);
}

export function minutesToClock(minutes: number): string {
  return `${pad(Math.floor(minutes / 60) % 24)}:${pad(minutes % 60)}`;
}

export function clockToMinutes(value: string): number {
  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + minutes;
}

export function greeting(date: Date): string {
  const hour = date.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export function relativeDay(value: string, now: Date = new Date()): string {
  const diff = Math.round((startOfDay(parseNaive(value)).getTime() - startOfDay(now).getTime()) / 86_400_000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  return formatDay(value, "short");
}
