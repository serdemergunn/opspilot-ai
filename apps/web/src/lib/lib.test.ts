import { describe, expect, it } from "vitest";
import { analyticsQuery } from "../api/client";
import { percentAxis } from "../features/overview/charts";
import { addDays, daysInRange, isWithin, previousPeriod, resolvePreset } from "./dateRange";
import { formatInt, formatPct, formatRange, pointDelta, relativeDelta } from "./format";

describe("date ranges", () => {
  it("adds days across month and year boundaries", () => {
    expect(addDays("2026-11-01", -1)).toBe("2026-10-31");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-03-29", 1)).toBe("2026-03-30"); // DST day in Europe is irrelevant: UTC arithmetic
  });

  it("resolves presets to complete days ending yesterday", () => {
    expect(resolvePreset("last7", "2026-11-11")).toEqual({ start: "2026-11-04", end: "2026-11-10" });
    expect(resolvePreset("yesterday", "2026-11-11")).toEqual({ start: "2026-11-10", end: "2026-11-10" });
    expect(daysInRange(resolvePreset("last90", "2026-11-11"))).toBe(90);
  });

  it("computes the equally long previous period", () => {
    expect(previousPeriod({ start: "2026-11-04", end: "2026-11-10" })).toEqual({ start: "2026-10-28", end: "2026-11-03" });
    expect(previousPeriod({ start: "2026-11-10", end: "2026-11-10" })).toEqual({ start: "2026-11-09", end: "2026-11-09" });
  });

  it("detects ranges outside the dataset", () => {
    expect(isWithin({ start: "2026-08-13", end: "2026-11-10" }, "2026-08-13", "2026-11-10")).toBe(true);
    expect(isWithin({ start: "2026-08-12", end: "2026-08-12" }, "2026-08-13", "2026-11-10")).toBe(false);
    expect(isWithin({ start: "2026-11-04", end: "2026-11-10" }, null, null)).toBe(false);
  });
});

describe("formatting", () => {
  it("never invents values for missing metrics", () => {
    expect(formatPct(null)).toBe("—");
    expect(formatInt(undefined)).toBe("—");
  });

  it("keeps the API's rounding and adds units", () => {
    expect(formatPct(40.3)).toBe("40.3%");
    expect(formatPct(68)).toBe("68.0%");
    expect(formatInt(1263973)).toBe("1,263,973");
  });

  it("formats ranges", () => {
    expect(formatRange("2026-11-04", "2026-11-10")).toBe("Nov 4 – Nov 10, 2026");
    expect(formatRange("2026-11-10", "2026-11-10")).toBe("Nov 10, 2026");
  });

  it("computes deltas with explicit units", () => {
    expect(pointDelta(79.8, 83.1)).toEqual({ value: -3.3, direction: "down", label: "−3.3 pp" });
    expect(relativeDelta(110, 100)).toEqual({ value: 10, direction: "up", label: "+10.0%" });
    expect(relativeDelta(5, 0)).toBeNull();
    expect(pointDelta(null, 4)).toBeNull();
  });
});

describe("api query strings", () => {
  it("encodes ranges and optional line filters", () => {
    expect(analyticsQuery({ start: "2026-11-04", end: "2026-11-10" })).toBe("startDate=2026-11-04&endDate=2026-11-10");
    expect(analyticsQuery({ start: "2026-11-04", end: "2026-11-10" }, ["L02", "L04"], { topN: "20" })).toBe(
      "startDate=2026-11-04&endDate=2026-11-10&topN=20&lineCodes=L02%2CL04",
    );
  });
});

describe("percent axis", () => {
  it("uses round bounds and regular ticks", () => {
    expect(percentAxis([72.4, 84.9])).toEqual({ domain: [70, 90], ticks: [70, 75, 80, 85, 90] });
  });
  it("caps at 100 and widens the step for large spans", () => {
    expect(percentAxis([40, 99])).toEqual({ domain: [35, 100], ticks: [40, 50, 60, 70, 80, 90, 100] });
  });
});
