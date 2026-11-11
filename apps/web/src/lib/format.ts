// Display formatting only. Values arrive already rounded by the API (metric definitions v1);
// these helpers never re-round reported metrics, they only add grouping and units.

const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const oneDecimal = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const monthDay = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
const longDate = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });

export const NOT_AVAILABLE = "—";

export const formatInt = (n: number | null | undefined) => (n == null ? NOT_AVAILABLE : integer.format(n));

export const formatPct = (n: number | null | undefined) => (n == null ? NOT_AVAILABLE : `${oneDecimal.format(n)}%`);

export const formatHours = (n: number | null | undefined) => (n == null ? NOT_AVAILABLE : `${oneDecimal.format(n)} h`);

export const formatMinutes = (n: number | null | undefined) => (n == null ? NOT_AVAILABLE : `${integer.format(n)} min`);

export const formatDay = (iso: string) => monthDay.format(new Date(`${iso}T00:00:00Z`));

export const formatLongDate = (iso: string) => longDate.format(new Date(`${iso}T00:00:00Z`));

export const formatRange = (start: string, end: string) =>
  start === end ? formatLongDate(start) : `${formatDay(start)} – ${formatLongDate(end)}`;

/** Change between two values, for period-over-period deltas. */
export interface Delta {
  /** Absolute difference for rates (percentage points); relative change (%) for quantities. */
  value: number;
  direction: "up" | "down" | "flat";
  label: string;
}

/** Relative change for quantities, e.g. produced units: +3.4%. Null when the base is zero or missing. */
export function relativeDelta(current: number | null, previous: number | null): Delta | null {
  if (current == null || previous == null || previous === 0) return null;
  const value = Math.round(((current - previous) / previous) * 1000) / 10;
  return { value, direction: direction(value), label: `${sign(value)}${oneDecimal.format(Math.abs(value))}%` };
}

/** Absolute change for rates already expressed in percent, e.g. attainment: −3.3 pp. */
export function pointDelta(current: number | null, previous: number | null): Delta | null {
  if (current == null || previous == null) return null;
  const value = Math.round((current - previous) * 10) / 10;
  return { value, direction: direction(value), label: `${sign(value)}${oneDecimal.format(Math.abs(value))} pp` };
}

const direction = (v: number): Delta["direction"] => (v > 0 ? "up" : v < 0 ? "down" : "flat");
const sign = (v: number) => (v > 0 ? "+" : v < 0 ? "−" : "±");
