"""Independent reference implementation of OpsPilot metric definitions (the "oracle").

Implements docs/architecture/metric-definitions.md (version 1) directly over the CSV files, using
only the Python standard library. It is intentionally simple and shares no code with the API or
the AI service, so it can be used to check both.

Scope: the demo plant time zone is UTC, so plant-local dates map to UTC days. Time zone
conversion is the API's responsibility and is tested there.

Usage:
    python sample-data/reference_metrics.py --write-golden   # regenerate golden/expected_metrics.json
    python sample-data/reference_metrics.py --check          # fail if the golden file is stale
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

METRIC_DEFINITIONS_VERSION = "1"
ROOT = Path(__file__).resolve().parent
CSV_DIR = ROOT / "csv"
GOLDEN_PATH = ROOT / "golden" / "expected_metrics.json"


# --------------------------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------------------------

def parse_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Line:
    code: str
    name: str
    is_active: bool


@dataclass(frozen=True)
class Reason:
    code: str
    name: str
    category: str
    is_planned: bool


@dataclass(frozen=True)
class ProductionRecord:
    line_code: str
    period_start: datetime
    planned: int
    produced: int
    defective: int


@dataclass(frozen=True)
class DowntimeEvent:
    line_code: str
    start: datetime
    end: datetime
    reason_code: str


@dataclass
class Dataset:
    lines: list[Line]
    reasons: dict[str, Reason]
    production: list[ProductionRecord]
    downtime: list[DowntimeEvent]


def _rows(name: str, csv_dir: Path) -> list[dict]:
    with (csv_dir / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_dataset(csv_dir: Path = CSV_DIR) -> Dataset:
    return Dataset(
        lines=[Line(r["Code"], r["Name"], r["IsActive"] == "true") for r in _rows("production_lines.csv", csv_dir)],
        reasons={r["Code"]: Reason(r["Code"], r["Name"], r["Category"], r["IsPlanned"] == "true")
                 for r in _rows("downtime_reasons.csv", csv_dir)},
        production=[ProductionRecord(r["LineCode"], parse_utc(r["PeriodStartUtc"]), int(r["PlannedQuantity"]),
                                     int(r["ProducedQuantity"]), int(r["DefectiveQuantity"]))
                    for r in _rows("production_records.csv", csv_dir)],
        downtime=[DowntimeEvent(r["LineCode"], parse_utc(r["StartTimeUtc"]), parse_utc(r["EndTimeUtc"]),
                                r["ReasonCode"])
                  for r in _rows("downtime_events.csv", csv_dir)],
    )


# --------------------------------------------------------------------------------------------
# Helpers that encode the metric definitions
# --------------------------------------------------------------------------------------------

def utc_window(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    """Inclusive plant-local dates -> half-open UTC interval (plant time zone = UTC)."""
    return (datetime.combine(start_date, time(), timezone.utc),
            datetime.combine(end_date + timedelta(days=1), time(), timezone.utc))


def round1(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def pct(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round1(Decimal(numerator) * 100 / Decimal(denominator))


def hours(minutes: int) -> float:
    return round1(Decimal(minutes) / 60)


def clipped_minutes(event: DowntimeEvent, start: datetime, end: datetime) -> int:
    overlap = min(event.end, end) - max(event.start, start)
    return max(0, int(overlap.total_seconds() // 60))


def _selected_lines(ds: Dataset, line_codes: list[str] | None) -> list[Line]:
    active = [l for l in ds.lines if l.is_active]
    if line_codes is None:
        return active
    unknown = set(line_codes) - {l.code for l in ds.lines}
    if unknown:
        raise ValueError(f"unknown line codes: {sorted(unknown)}")
    return [l for l in active if l.code in set(line_codes)]


def _downtime_in_window(ds, start, end, line_set, include_planned):
    for e in ds.downtime:
        if e.line_code not in line_set:
            continue
        if not include_planned and ds.reasons[e.reason_code].is_planned:
            continue
        m = clipped_minutes(e, start, end)
        if m > 0:
            yield e, m


def _top(items: list[dict], top_n: int) -> tuple[list[dict], int]:
    return items[:top_n], max(0, len(items) - top_n)


# --------------------------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------------------------

def production_summary(ds: Dataset, start_date: date, end_date: date, line_codes: list[str] | None = None) -> dict:
    start, end = utc_window(start_date, end_date)
    lines = _selected_lines(ds, line_codes)
    acc = {l.code: {"planned": 0, "produced": 0, "defective": 0, "records": 0, "downtime": 0} for l in lines}
    for r in ds.production:
        if r.line_code in acc and start <= r.period_start < end:
            a = acc[r.line_code]
            a["planned"] += r.planned
            a["produced"] += r.produced
            a["defective"] += r.defective
            a["records"] += 1
    for e, m in _downtime_in_window(ds, start, end, set(acc), include_planned=True):
        acc[e.line_code]["downtime"] += m

    def shape(a: dict) -> dict:
        return {
            "planned_quantity": a["planned"],
            "produced_quantity": a["produced"],
            "defective_quantity": a["defective"],
            "good_quantity": a["produced"] - a["defective"],
            "attainment_pct": pct(a["produced"], a["planned"]),
            "defect_rate_pct": pct(a["defective"], a["produced"]),
            "downtime_minutes": a["downtime"],
            "downtime_hours": hours(a["downtime"]),
            "record_count": a["records"],
        }

    totals = {k: sum(a[k] for a in acc.values()) for k in ("planned", "produced", "defective", "records", "downtime")}
    return {
        "totals": shape(totals),
        "by_line": [{"line_code": l.code, "line_name": l.name, **shape(acc[l.code])} for l in lines],
    }


def downtime_by_line(ds: Dataset, start_date: date, end_date: date, line_codes: list[str] | None = None,
                     include_planned: bool = True, top_n: int = 10) -> dict:
    start, end = utc_window(start_date, end_date)
    lines = _selected_lines(ds, line_codes)
    minutes = {l.code: 0 for l in lines}
    counts = {l.code: 0 for l in lines}
    for e, m in _downtime_in_window(ds, start, end, set(minutes), include_planned):
        minutes[e.line_code] += m
        counts[e.line_code] += 1
    total = sum(minutes.values())
    items = [{"line_code": l.code, "line_name": l.name, "downtime_minutes": minutes[l.code],
              "downtime_hours": hours(minutes[l.code]), "event_count": counts[l.code],
              "share_pct": pct(minutes[l.code], total)} for l in lines]
    items.sort(key=lambda i: (-i["downtime_minutes"], i["line_code"]))
    items, omitted = _top(items, top_n)
    return {"total_downtime_minutes": total, "items": items, "omitted_count": omitted}


def downtime_reasons(ds: Dataset, start_date: date, end_date: date, line_codes: list[str] | None = None,
                     include_planned: bool = True, top_n: int = 10) -> dict:
    start, end = utc_window(start_date, end_date)
    lines = _selected_lines(ds, line_codes)
    minutes: dict[str, int] = {}
    counts: dict[str, int] = {}
    for e, m in _downtime_in_window(ds, start, end, {l.code for l in lines}, include_planned):
        minutes[e.reason_code] = minutes.get(e.reason_code, 0) + m
        counts[e.reason_code] = counts.get(e.reason_code, 0) + 1
    total = sum(minutes.values())
    items = []
    for code, m in minutes.items():
        reason = ds.reasons[code]
        items.append({"reason_code": code, "reason_name": reason.name, "category": reason.category,
                      "is_planned": reason.is_planned, "downtime_minutes": m, "downtime_hours": hours(m),
                      "event_count": counts[code], "share_pct": pct(m, total)})
    items.sort(key=lambda i: (-i["downtime_minutes"], i["reason_code"]))
    items, omitted = _top(items, top_n)
    return {"total_downtime_minutes": total, "items": items, "omitted_count": omitted}


def daily_trend(ds: Dataset, start_date: date, end_date: date, line_codes: list[str] | None = None) -> dict:
    lines = {l.code for l in _selected_lines(ds, line_codes)}
    items = []
    day = start_date
    while day <= end_date:
        start, end = utc_window(day, day)
        planned = produced = defective = 0
        for r in ds.production:
            if r.line_code in lines and start <= r.period_start < end:
                planned, produced, defective = planned + r.planned, produced + r.produced, defective + r.defective
        downtime = sum(m for _, m in _downtime_in_window(ds, start, end, lines, include_planned=True))
        items.append({"date": day.isoformat(), "planned_quantity": planned, "produced_quantity": produced,
                      "defective_quantity": defective, "good_quantity": produced - defective,
                      "attainment_pct": pct(produced, planned), "defect_rate_pct": pct(defective, produced),
                      "downtime_minutes": downtime})
        day += timedelta(days=1)
    return {"items": items}


TOOLS = {
    "get_production_summary": production_summary,
    "get_downtime_by_line": downtime_by_line,
    "get_downtime_reasons": downtime_reasons,
    "get_daily_production_trend": daily_trend,
}


def run_tool(ds: Dataset, tool: str, arguments: dict) -> dict:
    """Call a tool with tool-style (JSON) arguments, as the agent would."""
    kwargs = dict(arguments)
    kwargs["start_date"] = date.fromisoformat(kwargs["start_date"])
    kwargs["end_date"] = date.fromisoformat(kwargs["end_date"])
    return TOOLS[tool](ds, **kwargs)


# --------------------------------------------------------------------------------------------
# Golden values
# --------------------------------------------------------------------------------------------

WINDOWS = {
    "last_7_days": ("2026-11-04", "2026-11-10"),
    "yesterday": ("2026-11-10", "2026-11-10"),
    "day_before_yesterday": ("2026-11-09", "2026-11-09"),
    "last_30_days": ("2026-10-12", "2026-11-10"),
    "full_dataset": ("2026-08-13", "2026-11-10"),
}


def golden_cases() -> list[tuple[str, str, dict]]:
    cases = []
    for name, (s, e) in WINDOWS.items():
        base = {"start_date": s, "end_date": e}
        cases.append((f"production_summary.{name}", "get_production_summary", base))
        cases.append((f"downtime_by_line.{name}", "get_downtime_by_line", base))
        cases.append((f"downtime_by_line.{name}.unplanned", "get_downtime_by_line", {**base, "include_planned": False}))
        cases.append((f"downtime_reasons.{name}", "get_downtime_reasons", base))
        cases.append((f"daily_trend.{name}", "get_daily_production_trend", base))
    s, e = WINDOWS["last_7_days"]
    cases.append(("downtime_reasons.last_7_days.L04", "get_downtime_reasons",
                  {"start_date": s, "end_date": e, "line_codes": ["L04"]}))
    cases.append(("production_summary.yesterday.L02", "get_production_summary",
                  {"start_date": "2026-11-10", "end_date": "2026-11-10", "line_codes": ["L02"]}))
    cases.append(("daily_trend.last_30_days.L02_L04", "get_daily_production_trend",
                  {"start_date": "2026-10-12", "end_date": "2026-11-10", "line_codes": ["L02", "L04"]}))
    cases.append(("downtime_by_line.last_7_days.top3", "get_downtime_by_line",
                  {"start_date": s, "end_date": e, "top_n": 3}))
    return cases


def build_golden(ds: Dataset) -> dict:
    return {
        "metric_definitions_version": METRIC_DEFINITIONS_VERSION,
        "reference_time_utc": "2026-11-11T00:00:00Z",
        "plant_timezone": "UTC",
        "cases": [{"id": cid, "tool": tool, "arguments": args, "expected": run_tool(ds, tool, args)}
                  for cid, tool, args in golden_cases()],
    }


def golden_text(ds: Dataset) -> str:
    return json.dumps(build_golden(ds), indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="OpsPilot reference metrics (oracle)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write-golden", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()

    text = golden_text(load_dataset())
    if args.write_golden:
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {GOLDEN_PATH.relative_to(ROOT.parent)}")
        return 0
    if not GOLDEN_PATH.exists() or GOLDEN_PATH.read_text(encoding="utf-8") != text:
        print("golden file is stale: run --write-golden and review the diff", file=sys.stderr)
        return 1
    print("golden file is up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
