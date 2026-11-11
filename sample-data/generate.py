"""Deterministic synthetic dataset generator for OpsPilot AI.

Generates a fictional manufacturing plant (6 lines, 90 days, hourly production) as CSV files.
Standard library only, so the dataset can be regenerated and verified without installing anything.

Usage:
    python sample-data/generate.py              # write CSVs to sample-data/csv
    python sample-data/generate.py --out DIR    # write somewhere else (used by tests)

Every random stream is seeded from a fixed string, so output is byte-for-byte reproducible.
All timestamps are UTC and minute-aligned. All names and records are fictional.
"""

from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = "opspilot-v1"
DATASET_END = datetime(2026, 11, 11, tzinfo=timezone.utc)  # pinned reference time (exclusive)
DATASET_DAYS = 90
DATASET_START = DATASET_END - timedelta(days=DATASET_DAYS)

DEFAULT_OUT = Path(__file__).resolve().parent / "csv"

# --------------------------------------------------------------------------------------------
# Catalogs
# --------------------------------------------------------------------------------------------

# code, name, department, nominal units per hour, base unplanned events per day, base defect rate
LINES = [
    ("L01", "Line 01", "Assembly", 120, 1.4, 0.012),
    ("L02", "Line 02", "Assembly", 110, 1.5, 0.014),
    ("L03", "Line 03", "Packaging", 180, 1.3, 0.016),
    ("L04", "Line 04", "Machining", 60, 1.8, 0.020),
    ("L05", "Line 05", "Machining", 65, 1.5, 0.018),
    ("L06", "Line 06", "Packaging", 170, 1.2, 0.013),
]

EQUIPMENT_BY_DEPARTMENT = {
    "Assembly": [("Conveyor", "Conveyor"), ("Robotic Arm", "Robot"),
                 ("Screwdriving Station", "Station"), ("Vision Inspector", "Inspection")],
    "Machining": [("CNC Mill", "CNC"), ("CNC Lathe", "CNC"),
                  ("Coolant System", "Utility"), ("Tool Changer", "Tooling")],
    "Packaging": [("Filler", "Filler"), ("Seal Bar Unit", "Sealer"),
                  ("Labeler", "Labeler"), ("Palletizer", "Robot")],
}

# code, name, category, is_planned
DOWNTIME_REASONS = [
    ("MECH_FAILURE", "Mechanical failure", "Equipment", False),
    ("ELEC_FAULT", "Electrical fault", "Equipment", False),
    ("MATERIAL_SHORTAGE", "Material shortage", "Logistics", False),
    ("QUALITY_HOLD", "Quality hold", "Quality", False),
    ("OPERATOR_UNAVAIL", "Operator unavailable", "Staffing", False),
    ("CHANGEOVER", "Product changeover", "Planned", True),
    ("PLANNED_MAINT", "Planned maintenance", "Planned", True),
]

# Unplanned reason weights and (min, mean extra) duration in minutes.
UNPLANNED_REASONS = {
    "MECH_FAILURE": (0.34, 15, 45),
    "ELEC_FAULT": (0.16, 10, 35),
    "MATERIAL_SHORTAGE": (0.22, 10, 25),
    "QUALITY_HOLD": (0.14, 15, 30),
    "OPERATOR_UNAVAIL": (0.14, 5, 15),
}

ERROR_CODES = {
    "E101": "Motor overload",
    "E102": "Conveyor jam",
    "E103": "Sensor misalignment",
    "E104": "Spindle overtemperature",
    "E105": "Hydraulic pressure low",
    "E106": "Vision system fault",
    "E107": "Servo drive fault",
    "E108": "Seal bar temperature deviation",
    "E109": "Emergency stop triggered",
    "E110": "PLC communication loss",
}

ERRORS_BY_EQUIPMENT_TYPE = {
    "Conveyor": (["E101", "E102", "E103"], ["E109", "E110"]),
    "Robot": (["E107", "E103"], ["E107", "E110"]),
    "Station": (["E101", "E103"], ["E107"]),
    "Inspection": (["E103"], ["E106", "E110"]),
    "CNC": (["E104", "E105", "E107"], ["E107", "E110"]),
    "Utility": (["E105", "E101"], ["E101"]),
    "Tooling": (["E103", "E105"], ["E107"]),
    "Filler": (["E102", "E105"], ["E110"]),
    "Sealer": (["E108", "E102"], ["E108", "E110"]),
    "Labeler": (["E102", "E103"], ["E106"]),
}

QUALITY_CATEGORIES = {
    "Assembly": ["Assembly defect", "Fastener torque deviation", "Surface defect", "Missing component"],
    "Machining": ["Dimensional deviation", "Surface finish defect", "Burr", "Tool mark"],
    "Packaging": ["Seal integrity", "Labeling error", "Fill level deviation", "Contamination"],
}
SEVERITIES = [("Low", 0.45), ("Medium", 0.35), ("High", 0.15), ("Critical", 0.05)]

# --------------------------------------------------------------------------------------------
# Seeded scenarios (documented in docs/architecture/phase-1-plan.md §3.3)
# --------------------------------------------------------------------------------------------

L04_SCENARIO_START = DATASET_END - timedelta(days=21)  # recurring E104 on L04-EQ02
L02_OUTAGE = (datetime(2026, 11, 10, 6, 0, tzinfo=timezone.utc),
              datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc))
L03_SCENARIO_START = DATASET_END - timedelta(days=30)  # seal integrity issues


# --------------------------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------------------------

@dataclass
class Downtime:
    line_code: str
    start: datetime
    end: datetime
    reason: str
    equipment_code: str | None
    description: str
    error_code: str | None = None
    id: int = 0

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


def rng(*parts: object) -> random.Random:
    """Independent, reproducible random stream per purpose (string seeds are hashed with SHA-512)."""
    return random.Random(":".join([SEED, *map(str, parts)]))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def floor_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def weighted(r: random.Random, items: list[tuple[str, float]]) -> str:
    x = r.random() * sum(w for _, w in items)
    for value, w in items:
        x -= w
        if x < 0:
            return value
    return items[-1][0]


# --------------------------------------------------------------------------------------------
# Generators
# --------------------------------------------------------------------------------------------

def build_equipment() -> list[dict]:
    rows = []
    for line_code, _, dept, *_ in LINES:
        for n, (name, eq_type) in enumerate(EQUIPMENT_BY_DEPARTMENT[dept], start=1):
            rows.append({"EquipmentCode": f"{line_code}-EQ{n:02d}", "LineCode": line_code,
                         "Name": name, "EquipmentType": eq_type})
    return rows


def generate_downtime(equipment: list[dict]) -> list[Downtime]:
    events: list[Downtime] = []
    eq_by_line: dict[str, list[dict]] = {}
    for e in equipment:
        eq_by_line.setdefault(e["LineCode"], []).append(e)

    for line_code, _, _, _, base_rate, _ in LINES:
        r = rng("downtime", line_code)
        line_events: list[Downtime] = []

        # Planned: one changeover per day at a random shift boundary, planned maintenance weekly.
        day = DATASET_START
        while day < DATASET_END:
            boundary = day + timedelta(hours=r.choice([6, 14, 22]))
            line_events.append(Downtime(line_code, boundary, boundary + timedelta(minutes=20 + r.randrange(41)),
                                        "CHANGEOVER", None, "Scheduled product changeover"))
            if day.weekday() == 6:  # Sunday
                start = day + timedelta(hours=2)
                eq = eq_by_line[line_code][r.randrange(4)]
                line_events.append(Downtime(line_code, start, start + timedelta(minutes=90 + r.randrange(91)),
                                            "PLANNED_MAINT", eq["EquipmentCode"],
                                            f"Preventive maintenance on {eq['Name']}"))
            day += timedelta(days=1)

        # Unplanned: Poisson arrivals; Line 04 failure rate triples in the scenario window.
        t = DATASET_START
        while True:
            rate = base_rate
            if line_code == "L04" and t >= L04_SCENARIO_START:
                rate *= 2.2
            t = t + timedelta(hours=r.expovariate(rate / 24.0))
            if t >= DATASET_END:
                break
            start = floor_minute(t)
            reason_weights = [(k, v[0]) for k, v in UNPLANNED_REASONS.items()]
            if line_code == "L04" and start >= L04_SCENARIO_START:
                reason_weights = [(k, w * (3.0 if k == "MECH_FAILURE" else 1.0)) for k, w in reason_weights]
            reason = weighted(r, reason_weights)
            _, min_dur, mean_extra = UNPLANNED_REASONS[reason]
            minutes = min_dur + int(r.expovariate(1.0 / mean_extra))
            eq_code, error_code, desc = None, None, None
            if reason in ("MECH_FAILURE", "ELEC_FAULT"):
                if line_code == "L04" and reason == "MECH_FAILURE" and start >= L04_SCENARIO_START and r.random() < 0.8:
                    eq = eq_by_line["L04"][1]  # L04-EQ02, CNC Lathe
                    error_code = "E104"
                    minutes += 30 + r.randrange(60)
                else:
                    eq = eq_by_line[line_code][r.randrange(4)]
                    mech, elec = ERRORS_BY_EQUIPMENT_TYPE[eq["EquipmentType"]]
                    error_code = r.choice(mech if reason == "MECH_FAILURE" else elec)
                eq_code = eq["EquipmentCode"]
                desc = f"{eq['Name']} stopped: {ERROR_CODES[error_code]} ({error_code})"
            elif reason == "MATERIAL_SHORTAGE":
                desc = r.choice(["Upstream material not delivered", "Component stock depleted at line side",
                                 "Packaging material shortage"])
            elif reason == "QUALITY_HOLD":
                desc = r.choice(["Line held pending first-article inspection", "Hold after out-of-spec sample",
                                 "Quality hold for batch verification"])
            else:
                desc = r.choice(["Shift handover delay", "Operator reassigned to another line",
                                 "Break coverage unavailable"])
            line_events.append(Downtime(line_code, start, start + timedelta(minutes=minutes), reason, eq_code,
                                        desc, error_code))

        if line_code == "L02":
            line_events.append(Downtime("L02", *L02_OUTAGE, "ELEC_FAULT", "L02-EQ01",
                                        "Conveyor stopped: PLC communication loss (E110), main drive cabinet",
                                        "E110"))

        events.extend(resolve_overlaps(line_events))

    events = [e for e in events if e.end <= DATASET_END]
    events.sort(key=lambda e: (e.start, e.line_code))
    for i, e in enumerate(events, start=1):
        e.id = i
    return events


def resolve_overlaps(events: list[Downtime]) -> list[Downtime]:
    """Keep a non-overlapping set per line. Scenario outages win; otherwise earlier events win."""
    forced = [e for e in events if e.line_code == "L02" and (e.start, e.end) == L02_OUTAGE]
    kept: list[Downtime] = list(forced)
    for e in sorted(events, key=lambda e: (e.start, e.reason)):
        if e in forced:
            continue
        if all(e.end <= k.start or e.start >= k.end for k in kept):
            kept.append(e)
    return kept


def generate_production(events: list[Downtime]) -> list[dict]:
    down_by_hour: dict[tuple[str, datetime], int] = {}
    for e in events:
        cursor = e.start
        while cursor < e.end:
            hour = cursor.replace(minute=0)
            seg_end = min(e.end, hour + timedelta(hours=1))
            key = (e.line_code, hour)
            down_by_hour[key] = down_by_hour.get(key, 0) + int((seg_end - cursor).total_seconds() // 60)
            cursor = seg_end

    rows = []
    hours = DATASET_DAYS * 24
    for line_code, _, _, nominal, _, defect_rate in LINES:
        r = rng("production", line_code)
        for h in range(hours):
            period = DATASET_START + timedelta(hours=h)
            run_minutes = 60 - down_by_hour.get((line_code, period), 0)
            performance = 0.86 + 0.10 * r.random()
            produced = int(nominal / 60 * run_minutes * performance)
            rate = defect_rate
            if line_code == "L03" and period >= L03_SCENARIO_START:
                rate *= 2.6
            defective = min(produced, int(produced * rate * (0.4 + 1.2 * r.random()) + 0.5))
            rows.append({"LineCode": line_code, "PeriodStartUtc": iso(period), "PlannedQuantity": nominal,
                         "ProducedQuantity": produced, "DefectiveQuantity": defective})
    rows.sort(key=lambda x: (x["PeriodStartUtc"], x["LineCode"]))
    return rows


def generate_maintenance(events: list[Downtime], equipment: list[dict]) -> list[dict]:
    eq = {e["EquipmentCode"]: e for e in equipment}
    r = rng("maintenance")
    rows = []
    for e in events:
        if e.equipment_code is None:
            continue
        if e.reason == "PLANNED_MAINT":
            desc, resolution, code = e.description, "Preventive checklist completed; no defects found", None
        else:
            code = e.error_code
            desc = f"{ERROR_CODES[code]} on {eq[e.equipment_code]['Name']}"
            resolution = {
                "E104": r.choice(["Cleaned spindle cooling channels and reset thermal sensor",
                                  "Replaced spindle cooling fan; temperature normal after restart",
                                  "Reduced spindle load and scheduled bearing inspection"]),
                "E110": "Replaced faulty network switch in drive cabinet; PLC link restored",
            }.get(code, r.choice(["Component adjusted and tested", "Faulty part replaced",
                                  "Reset and recalibrated; monitored for 30 minutes"]))
        rows.append({"EquipmentCode": e.equipment_code, "DowntimeEventId": e.id,
                     "OccurredAtUtc": iso(e.start), "ErrorCode": code or "", "Description": desc,
                     "Resolution": resolution, "DurationMinutes": e.minutes})
    rows.sort(key=lambda x: (x["OccurredAtUtc"], x["EquipmentCode"]))
    for i, row in enumerate(rows, start=1):
        row["Id"] = i
    return rows


def generate_quality(lines_by_code: dict[str, tuple]) -> list[dict]:
    rows = []
    for line_code, (_, _, dept, *_rest) in lines_by_code.items():
        r = rng("quality", line_code)
        t = DATASET_START
        while True:
            boosted = line_code == "L03" and t >= L03_SCENARIO_START
            t = t + timedelta(hours=r.expovariate((0.9 if boosted else 0.2) / 24.0))
            if t >= DATASET_END:
                break
            ts = floor_minute(t)
            category = "Seal integrity" if boosted and r.random() < 0.7 else r.choice(QUALITY_CATEGORIES[dept])
            severity = weighted(r, SEVERITIES)
            age_days = (DATASET_END - ts).days
            if age_days > 14:
                status = "Resolved" if r.random() < 0.95 else "Investigating"
            else:
                status = weighted(r, [("Open", 0.4), ("Investigating", 0.35), ("Resolved", 0.25)])
            rows.append({"LineCode": line_code, "OccurredAtUtc": iso(ts), "Category": category,
                         "Severity": severity, "Status": status,
                         "Description": f"{category} detected during in-process inspection on {line_code}"})
    rows.sort(key=lambda x: (x["OccurredAtUtc"], x["LineCode"]))
    for i, row in enumerate(rows, start=1):
        row["Id"] = i
    return rows


# --------------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------------

def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(columns)
        for row in rows:
            w.writerow([row[c] for c in columns])


def generate(out: Path) -> dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    lines_by_code = {l[0]: l for l in LINES}
    equipment = build_equipment()
    events = generate_downtime(equipment)
    production = generate_production(events)
    maintenance = generate_maintenance(events, equipment)
    quality = generate_quality(lines_by_code)

    write_csv(out / "production_lines.csv", ["Code", "Name", "Department", "NominalRatePerHour", "IsActive"],
              [{"Code": c, "Name": n, "Department": d, "NominalRatePerHour": rate, "IsActive": "true"}
               for c, n, d, rate, *_ in LINES])
    write_csv(out / "equipment.csv", ["EquipmentCode", "LineCode", "Name", "EquipmentType"], equipment)
    write_csv(out / "downtime_reasons.csv", ["Code", "Name", "Category", "IsPlanned"],
              [{"Code": c, "Name": n, "Category": cat, "IsPlanned": str(p).lower()}
               for c, n, cat, p in DOWNTIME_REASONS])
    write_csv(out / "production_records.csv",
              ["LineCode", "PeriodStartUtc", "PlannedQuantity", "ProducedQuantity", "DefectiveQuantity"], production)
    write_csv(out / "downtime_events.csv",
              ["Id", "LineCode", "EquipmentCode", "StartTimeUtc", "EndTimeUtc", "DurationMinutes", "ReasonCode",
               "Description"],
              [{"Id": e.id, "LineCode": e.line_code, "EquipmentCode": e.equipment_code or "",
                "StartTimeUtc": iso(e.start), "EndTimeUtc": iso(e.end), "DurationMinutes": e.minutes,
                "ReasonCode": e.reason, "Description": e.description} for e in events])
    write_csv(out / "quality_incidents.csv",
              ["Id", "LineCode", "OccurredAtUtc", "Category", "Severity", "Status", "Description"], quality)
    write_csv(out / "maintenance_events.csv",
              ["Id", "EquipmentCode", "DowntimeEventId", "OccurredAtUtc", "ErrorCode", "Description", "Resolution",
               "DurationMinutes"], maintenance)
    return {"production_lines": len(LINES), "equipment": len(equipment), "production_records": len(production),
            "downtime_events": len(events), "quality_incidents": len(quality), "maintenance_events": len(maintenance)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    for table, count in generate(args.out).items():
        print(f"{table:20} {count:>6}")


if __name__ == "__main__":
    main()
