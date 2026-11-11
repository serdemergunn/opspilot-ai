// Mirrors the camelCase public API of apps/api (see docs/architecture/phase-1-plan.md §4.1).

export interface QueryMeta {
  windowStartUtc: string;
  windowEndUtc: string;
  rowCount: number;
  truncated: boolean;
  queryMs: number;
  source: string;
  metricDefinitionsVersion: string;
}

export interface Envelope<T> {
  data: T;
  meta: QueryMeta;
}

export interface ProductionMetrics {
  plannedQuantity: number;
  producedQuantity: number;
  defectiveQuantity: number;
  goodQuantity: number;
  attainmentPct: number | null;
  defectRatePct: number | null;
  downtimeMinutes: number;
  downtimeHours: number;
  recordCount: number;
}

export interface LineProductionMetrics extends ProductionMetrics {
  lineCode: string;
  lineName: string;
}

export interface ProductionSummary {
  totals: ProductionMetrics;
  byLine: LineProductionMetrics[];
}

export interface LineDowntime {
  lineCode: string;
  lineName: string;
  downtimeMinutes: number;
  downtimeHours: number;
  eventCount: number;
  sharePct: number | null;
}

export interface DowntimeByLine {
  totalDowntimeMinutes: number;
  items: LineDowntime[];
  omittedCount: number;
}

export interface ReasonDowntime {
  reasonCode: string;
  reasonName: string;
  category: string;
  isPlanned: boolean;
  downtimeMinutes: number;
  downtimeHours: number;
  eventCount: number;
  sharePct: number | null;
}

export interface DowntimeReasons {
  totalDowntimeMinutes: number;
  items: ReasonDowntime[];
  omittedCount: number;
}

export interface DailyPoint {
  date: string;
  plannedQuantity: number;
  producedQuantity: number;
  defectiveQuantity: number;
  goodQuantity: number;
  attainmentPct: number | null;
  defectRatePct: number | null;
  downtimeMinutes: number;
}

export interface DailyTrend {
  items: DailyPoint[];
}

export interface ApiMeta {
  referenceTimeUtc: string;
  clockPinned: boolean;
  today: string;
  plantTimeZone: string;
  dataset: { firstDate: string | null; lastDate: string | null };
  limits: { maxRangeDays: number; maxTopN: number };
}

export interface ProductionLine {
  code: string;
  name: string;
  department: string;
  isActive: boolean;
}

/** Inclusive plant-local date range (YYYY-MM-DD). */
export interface DateRange {
  start: string;
  end: string;
}
