import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "./client";
import type { DateRange } from "./types";

// Reference data changes only on reseed.
export const useMeta = () => useQuery({ queryKey: ["meta"], queryFn: ({ signal }) => api.meta(signal), staleTime: Infinity });
export const useLines = () => useQuery({ queryKey: ["lines"], queryFn: ({ signal }) => api.lines(signal), staleTime: Infinity });

// Analytics: keep the previous result on screen while a new range loads, so charts don't flash empty.
const analytics = { staleTime: 60_000, placeholderData: keepPreviousData } as const;

export const useProductionSummary = (range: DateRange | undefined, lines: string[]) =>
  useQuery({
    queryKey: ["production-summary", range, lines],
    queryFn: ({ signal }) => api.productionSummary(range!, lines, signal),
    enabled: range !== undefined,
    ...analytics,
  });

export const useDowntimeByLine = (range: DateRange | undefined, lines: string[]) =>
  useQuery({
    queryKey: ["downtime-by-line", range, lines],
    queryFn: ({ signal }) => api.downtimeByLine(range!, lines, signal),
    enabled: range !== undefined,
    ...analytics,
  });

export const useDowntimeReasons = (range: DateRange | undefined, lines: string[]) =>
  useQuery({
    queryKey: ["downtime-reasons", range, lines],
    queryFn: ({ signal }) => api.downtimeReasons(range!, lines, signal),
    enabled: range !== undefined,
    ...analytics,
  });

export const useDailyTrend = (range: DateRange | undefined, lines: string[]) =>
  useQuery({
    queryKey: ["daily-trend", range, lines],
    queryFn: ({ signal }) => api.dailyTrend(range!, lines, signal),
    enabled: range !== undefined,
    ...analytics,
  });
