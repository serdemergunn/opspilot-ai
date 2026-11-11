# Metric Definitions

Version: **1** · This is the single source of truth for every metric OpsPilot AI reports.
The C# implementation (`apps/api`) and the independent Python oracle
(`sample-data/reference_metrics.py`) must both follow it exactly. Changing a formula means
bumping the version, updating both implementations and regenerating the golden file.

## Time windows

- All stored timestamps are UTC.
- A request with plant-local dates `start_date`..`end_date` (inclusive) is converted to the
  half-open UTC interval `[start_date 00:00 local, (end_date + 1 day) 00:00 local)`.
- **Production records** are included when `PeriodStartUtc` lies inside the window.
  (Records are one-hour buckets aligned to the hour.)
- **Downtime events** are **clipped** to the window: an event contributes
  `max(0, min(End, windowEnd) − max(Start, windowStart))` minutes. An event *counts* toward
  `event_count` when that overlap is greater than zero. An outage that spans midnight therefore
  splits correctly between two days, and the sum over adjacent windows equals the total.

## Formulas

| Metric | Definition |
|---|---|
| `planned_quantity` | Σ `PlannedQuantity` |
| `produced_quantity` | Σ `ProducedQuantity` |
| `defective_quantity` | Σ `DefectiveQuantity` |
| `good_quantity` | `produced_quantity − defective_quantity` |
| `attainment_pct` | `produced_quantity / planned_quantity × 100`; `null` if planned is 0 |
| `defect_rate_pct` | `defective_quantity / produced_quantity × 100`; `null` if produced is 0 |
| `downtime_minutes` | Σ clipped minutes (integer, because all timestamps are minute-aligned) |
| `downtime_hours` | `downtime_minutes / 60` |
| `share_pct` | `group downtime_minutes / total downtime_minutes of the filtered set × 100`; `null` if total is 0. Computed **before** `top_n` truncation. |
| `record_count` | number of production records in the window |
| daily trend | the production and downtime formulas above, evaluated per plant-local day (each day is its own window) |

`include_planned = false` excludes events whose reason has `IsPlanned = 1`
(`CHANGEOVER`, `PLANNED_MAINT`) from downtime metrics. Production quantities are unaffected.

## Rounding

- Percentages and hours: **1 decimal place, round half away from zero**
  (C#: `Math.Round(x, 1, MidpointRounding.AwayFromZero)` on `decimal`; Python:
  `Decimal.quantize(Decimal("0.1"), ROUND_HALF_UP)`). Never use binary floating point or the
  .NET default banker's rounding for reported values.
- Rounding is applied once, at the output boundary, never to intermediate values.
- Because shares are rounded individually, they may sum to 99.9–100.1.

## Ordering

- By-line and by-reason lists are sorted by `downtime_minutes` descending, then by code ascending.
- `get_downtime_by_line` includes every selected active line, including lines with zero downtime.
- `get_downtime_reasons` includes only reasons with non-zero downtime.
- `omitted_count` = number of items removed by `top_n`.
