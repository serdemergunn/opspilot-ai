"""Reproducibility, integrity and scenario tests for the committed synthetic dataset."""

import csv
import json
import tempfile
import unittest
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from tests.data import _paths
import generate
import reference_metrics as rm

CSV_DIR = _paths.SAMPLE_DATA / "csv"


def read(name: str) -> list[dict]:
    with (CSV_DIR / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class ReproducibilityTests(unittest.TestCase):
    def test_generator_reproduces_committed_csvs_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate.generate(Path(tmp))
            committed = sorted(p.name for p in CSV_DIR.glob("*.csv"))
            self.assertEqual(committed, sorted(p.name for p in Path(tmp).glob("*.csv")))
            for name in committed:
                with self.subTest(file=name):
                    self.assertEqual((Path(tmp) / name).read_bytes(), (CSV_DIR / name).read_bytes())

    def test_golden_file_is_current(self):
        self.assertEqual(rm.GOLDEN_PATH.read_text(encoding="utf-8"), rm.golden_text(rm.load_dataset()))


class IntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines = read("production_lines.csv")
        cls.equipment = read("equipment.csv")
        cls.reasons = read("downtime_reasons.csv")
        cls.production = read("production_records.csv")
        cls.downtime = read("downtime_events.csv")
        cls.quality = read("quality_incidents.csv")
        cls.maintenance = read("maintenance_events.csv")

    def test_sizes_and_coverage(self):
        self.assertEqual(len(self.lines), 6)
        self.assertEqual(len(self.equipment), 24)
        self.assertEqual(len(self.production), 6 * 90 * 24)
        periods = sorted({r["PeriodStartUtc"] for r in self.production})
        self.assertEqual(periods[0], "2026-08-13T00:00:00Z")
        self.assertEqual(periods[-1], "2026-11-10T23:00:00Z")
        self.assertEqual(len({(r["LineCode"], r["PeriodStartUtc"]) for r in self.production}), len(self.production))

    def test_foreign_keys_resolve(self):
        lines = {l["Code"] for l in self.lines}
        equipment = {e["EquipmentCode"]: e for e in self.equipment}
        reasons = {r["Code"] for r in self.reasons}
        downtime = {d["Id"]: d for d in self.downtime}
        self.assertTrue({e["LineCode"] for e in self.equipment} <= lines)
        self.assertTrue({r["LineCode"] for r in self.production} <= lines)
        self.assertTrue({q["LineCode"] for q in self.quality} <= lines)
        for d in self.downtime:
            self.assertIn(d["LineCode"], lines)
            self.assertIn(d["ReasonCode"], reasons)
            if d["EquipmentCode"]:
                self.assertEqual(equipment[d["EquipmentCode"]]["LineCode"], d["LineCode"])
        for m in self.maintenance:
            self.assertIn(m["EquipmentCode"], equipment)
            self.assertEqual(downtime[m["DowntimeEventId"]]["EquipmentCode"], m["EquipmentCode"])

    def test_downtime_events_are_consistent_and_do_not_overlap(self):
        by_line = defaultdict(list)
        for d in self.downtime:
            start, end = rm.parse_utc(d["StartTimeUtc"]), rm.parse_utc(d["EndTimeUtc"])
            self.assertGreater(end, start)
            self.assertEqual(end - start, timedelta(minutes=int(d["DurationMinutes"])))
            self.assertEqual((start.second, end.second), (0, 0))
            self.assertLessEqual(d["EndTimeUtc"], "2026-11-11T00:00:00Z")
            by_line[d["LineCode"]].append((start, end))
        for line, spans in by_line.items():
            spans.sort()
            for (_, prev_end), (next_start, _) in zip(spans, spans[1:]):
                self.assertLessEqual(prev_end, next_start, f"overlap on {line} at {next_start}")

    def test_production_quantities_are_valid(self):
        for r in self.production:
            planned, produced, defective = (int(r[k]) for k in
                                            ("PlannedQuantity", "ProducedQuantity", "DefectiveQuantity"))
            self.assertTrue(0 <= defective <= produced <= planned, r)

    def test_categorical_values(self):
        self.assertTrue({q["Severity"] for q in self.quality} <= {"Low", "Medium", "High", "Critical"})
        self.assertTrue({q["Status"] for q in self.quality} <= {"Open", "Investigating", "Resolved"})
        self.assertTrue({m["ErrorCode"] for m in self.maintenance} <= set(generate.ERROR_CODES) | {""})


class ScenarioTests(unittest.TestCase):
    """The demo depends on these stories being present in the data."""

    @classmethod
    def setUpClass(cls):
        golden = json.loads(rm.GOLDEN_PATH.read_text(encoding="utf-8"))
        cls.cases = {c["id"]: c["expected"] for c in golden["cases"]}

    def test_line_04_leads_downtime_last_week_driven_by_mechanical_failure(self):
        self.assertEqual(self.cases["downtime_by_line.last_7_days"]["items"][0]["line_code"], "L04")
        self.assertEqual(self.cases["downtime_reasons.last_7_days.L04"]["items"][0]["reason_code"], "MECH_FAILURE")

    def test_line_02_outage_yesterday(self):
        l02 = self.cases["production_summary.yesterday.L02"]["totals"]
        self.assertGreaterEqual(l02["downtime_minutes"], 360)
        self.assertLess(self.cases["production_summary.yesterday"]["totals"]["attainment_pct"],
                        self.cases["production_summary.day_before_yesterday"]["totals"]["attainment_pct"])

    def test_line_03_has_highest_defect_rate_last_30_days(self):
        by_line = self.cases["production_summary.last_30_days"]["by_line"]
        self.assertEqual(max(by_line, key=lambda l: l["defect_rate_pct"])["line_code"], "L03")


if __name__ == "__main__":
    unittest.main()
