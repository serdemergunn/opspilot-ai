import type { DateRange } from "../api/types";

// Plant-local calendar dates as YYYY-MM-DD strings. Arithmetic runs in UTC so the browser's own
// time zone can never shift a date. "Today" always comes from the API (/api/meta), which applies
// the pinned demo clock and the plant time zone.

export type PresetId = "yesterday" | "last7" | "last30" | "last90";

export const PRESETS: { id: PresetId; label: string; days: number; comparison: string }[] = [
  { id: "yesterday", label: "Yesterday", days: 1, comparison: "vs the day before" },
  { id: "last7", label: "Last 7 days", days: 7, comparison: "vs the previous 7 days" },
  { id: "last30", label: "Last 30 days", days: 30, comparison: "vs the previous 30 days" },
  { id: "last90", label: "Last 90 days", days: 90, comparison: "vs the previous 90 days" },
];

export function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function daysInRange(range: DateRange): number {
  const ms = Date.parse(`${range.end}T00:00:00Z`) - Date.parse(`${range.start}T00:00:00Z`);
  return Math.round(ms / 86_400_000) + 1;
}

/** Complete days only: ranges end yesterday, because today is still in progress. */
export function resolvePreset(preset: PresetId, today: string): DateRange {
  const days = PRESETS.find((p) => p.id === preset)?.days ?? 7;
  const end = addDays(today, -1);
  return { start: addDays(end, -(days - 1)), end };
}

/** The equally long period immediately before `range`, used for period-over-period deltas. */
export function previousPeriod(range: DateRange): DateRange {
  const days = daysInRange(range);
  return { start: addDays(range.start, -days), end: addDays(range.start, -1) };
}

/** True when `range` lies fully inside the dataset, so a comparison is meaningful. */
export function isWithin(range: DateRange, first: string | null, last: string | null): boolean {
  return first !== null && last !== null && range.start >= first && range.end <= last;
}
