import type {
  ApiMeta,
  DailyTrend,
  DateRange,
  DowntimeByLine,
  DowntimeReasons,
  Envelope,
  ProductionLine,
  ProductionSummary,
} from "./types";

/** Error carrying the RFC 7807 problem details returned by the API. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly fieldErrors: Record<string, string[]> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { headers: { Accept: "application/json" }, signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "The API is unreachable. Is it running on 127.0.0.1:8080?");
  }
  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as
      | { title?: string; errors?: Record<string, string[]> }
      | null;
    if (!problem && response.status >= 500) {
      // No problem-details body: the API process itself did not answer (e.g. the dev proxy could not connect).
      throw new ApiError(response.status, `The API is not responding (HTTP ${response.status}). Is it running on 127.0.0.1:8080?`);
    }
    throw new ApiError(response.status, problem?.title ?? `Request failed (${response.status})`, problem?.errors ?? {});
  }
  return (await response.json()) as T;
}

export function analyticsQuery(range: DateRange, lineCodes: string[] = [], extra: Record<string, string> = {}): string {
  const params = new URLSearchParams({ startDate: range.start, endDate: range.end, ...extra });
  if (lineCodes.length > 0) params.set("lineCodes", lineCodes.join(","));
  return params.toString();
}

export const api = {
  meta: (signal?: AbortSignal) => getJson<ApiMeta>("/api/meta", signal),
  lines: (signal?: AbortSignal) => getJson<ProductionLine[]>("/api/lines", signal),
  productionSummary: (range: DateRange, lines: string[], signal?: AbortSignal) =>
    getJson<Envelope<ProductionSummary>>(`/api/analytics/production-summary?${analyticsQuery(range, lines)}`, signal),
  downtimeByLine: (range: DateRange, lines: string[], signal?: AbortSignal) =>
    getJson<Envelope<DowntimeByLine>>(`/api/analytics/downtime-by-line?${analyticsQuery(range, lines, { topN: "20" })}`, signal),
  downtimeReasons: (range: DateRange, lines: string[], signal?: AbortSignal) =>
    getJson<Envelope<DowntimeReasons>>(`/api/analytics/downtime-reasons?${analyticsQuery(range, lines, { topN: "20" })}`, signal),
  dailyTrend: (range: DateRange, lines: string[], signal?: AbortSignal) =>
    getJson<Envelope<DailyTrend>>(`/api/analytics/daily-trend?${analyticsQuery(range, lines)}`, signal),
};
