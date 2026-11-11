"""Hand-computed fixture tests for the metric oracle (docs/architecture/metric-definitions.md).

Every expected value below is worked out by hand in the comments, not produced by the code under test.
"""

import unittest
from datetime import date, datetime, timezone

from tests.data import _paths  # noqa: F401  (adds sample-data to sys.path)
import reference_metrics as rm
from reference_metrics import Dataset, DowntimeEvent, Line, ProductionRecord, Reason


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def fixture() -> Dataset:
    return Dataset(
        lines=[Line("L01", "Line 01", True), Line("L02", "Line 02", True), Line("L03", "Line 03", False)],
        reasons={
            "MECH_FAILURE": Reason("MECH_FAILURE", "Mechanical failure", "Equipment", False),
            "CHANGEOVER": Reason("CHANGEOVER", "Product changeover", "Planned", True),
        },
        production=[
            ProductionRecord("L01", utc(2026, 1, 2, 0), 100, 80, 3),
            ProductionRecord("L01", utc(2026, 1, 2, 1), 100, 90, 0),
            ProductionRecord("L02", utc(2026, 1, 2, 0), 50, 0, 0),
            ProductionRecord("L01", utc(2026, 1, 3, 0), 100, 100, 1),  # outside the 01-02 window
        ],
        downtime=[
            # 75 minutes spanning midnight: 30 min on 01-01, 45 min on 01-02
            DowntimeEvent("L01", utc(2026, 1, 1, 23, 30), utc(2026, 1, 2, 0, 45), "MECH_FAILURE"),
            DowntimeEvent("L01", utc(2026, 1, 2, 6, 0), utc(2026, 1, 2, 6, 30), "CHANGEOVER"),  # 30, planned
            DowntimeEvent("L02", utc(2026, 1, 2, 10, 0), utc(2026, 1, 2, 10, 5), "MECH_FAILURE"),  # 5
            DowntimeEvent("L03", utc(2026, 1, 2, 1, 0), utc(2026, 1, 2, 2, 0), "MECH_FAILURE"),  # inactive line
            # ends exactly at the window start: zero overlap, must not count as an event
            DowntimeEvent("L02", utc(2026, 1, 1, 22, 0), utc(2026, 1, 2, 0, 0), "MECH_FAILURE"),
        ],
    )


D1, D2, D3 = date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)


class RoundingTests(unittest.TestCase):
    def test_half_away_from_zero_not_bankers(self):
        self.assertEqual(rm.pct(1, 16), 6.3)  # 6.25 -> 6.3 (banker's would give 6.2)
        self.assertEqual(rm.pct(49, 400), 12.3)  # 12.25 -> 12.3
        self.assertEqual(rm.hours(9), 0.2)  # 0.15 -> 0.2 (binary float round() gives 0.1)
        self.assertEqual(rm.hours(15), 0.3)  # 0.25 -> 0.3

    def test_zero_denominator_is_null(self):
        self.assertIsNone(rm.pct(5, 0))


class DowntimeByLineTests(unittest.TestCase):
    def setUp(self):
        self.ds = fixture()

    def test_clips_to_window_and_counts_overlapping_events(self):
        r = rm.downtime_by_line(self.ds, D2, D2)
        # L01: 45 (clipped) + 30 = 75, 2 events; L02: 5, 1 event (the 22:00-00:00 event has zero overlap)
        self.assertEqual(r["total_downtime_minutes"], 80)
        self.assertEqual([(i["line_code"], i["downtime_minutes"], i["event_count"]) for i in r["items"]],
                         [("L01", 75, 2), ("L02", 5, 1)])
        # 75/80 = 93.75 -> 93.8 ; 5/80 = 6.25 -> 6.3
        self.assertEqual([i["share_pct"] for i in r["items"]], [93.8, 6.3])
        self.assertEqual(r["items"][0]["downtime_hours"], 1.3)  # 75/60 = 1.25 -> 1.3

    def test_adjacent_windows_are_additive(self):
        day1 = rm.downtime_by_line(self.ds, D1, D1)["items"]
        day2 = rm.downtime_by_line(self.ds, D2, D2)["items"]
        both = rm.downtime_by_line(self.ds, D1, D2)["items"]
        by = lambda items: {i["line_code"]: i["downtime_minutes"] for i in items}  # noqa: E731
        self.assertEqual(by(day1)["L01"], 30)
        self.assertEqual(by(both)["L01"], by(day1)["L01"] + by(day2)["L01"])
        # the spanning event is one event, not two, in the combined window
        self.assertEqual({i["line_code"]: i["event_count"] for i in both}["L01"], 2)

    def test_excludes_planned_when_requested(self):
        r = rm.downtime_by_line(self.ds, D2, D2, include_planned=False)
        self.assertEqual(r["total_downtime_minutes"], 50)
        self.assertEqual([(i["line_code"], i["share_pct"]) for i in r["items"]], [("L01", 90.0), ("L02", 10.0)])

    def test_empty_window_lists_active_lines_with_zero_and_null_share(self):
        r = rm.downtime_by_line(self.ds, date(2026, 2, 1), date(2026, 2, 1))
        self.assertEqual(r["total_downtime_minutes"], 0)
        self.assertEqual([i["line_code"] for i in r["items"]], ["L01", "L02"])  # tie -> code ascending
        self.assertTrue(all(i["share_pct"] is None for i in r["items"]))

    def test_line_filter_and_inactive_lines(self):
        r = rm.downtime_by_line(self.ds, D2, D2, line_codes=["L02"])
        self.assertEqual([(i["line_code"], i["share_pct"]) for i in r["items"]], [("L02", 100.0)])
        self.assertEqual(rm.downtime_by_line(self.ds, D2, D2, line_codes=["L03"])["items"], [])

    def test_unknown_line_code_is_rejected(self):
        with self.assertRaises(ValueError):
            rm.downtime_by_line(self.ds, D2, D2, line_codes=["L99"])

    def test_top_n_truncates_after_share_calculation(self):
        r = rm.downtime_by_line(self.ds, D2, D2, top_n=1)
        self.assertEqual(len(r["items"]), 1)
        self.assertEqual(r["omitted_count"], 1)
        self.assertEqual(r["items"][0]["share_pct"], 93.8)  # still relative to the full total of 80


class DowntimeReasonsTests(unittest.TestCase):
    def test_groups_by_reason(self):
        r = rm.downtime_reasons(fixture(), D2, D2)
        # MECH: L01 45 + L02 5 = 50 (2 events) -> 62.5 ; CHANGEOVER 30 (1 event) -> 37.5
        self.assertEqual([(i["reason_code"], i["downtime_minutes"], i["event_count"], i["share_pct"], i["is_planned"])
                          for i in r["items"]],
                         [("MECH_FAILURE", 50, 2, 62.5, False), ("CHANGEOVER", 30, 1, 37.5, True)])

    def test_reasons_without_downtime_are_omitted(self):
        r = rm.downtime_reasons(fixture(), D2, D2, include_planned=False)
        self.assertEqual([i["reason_code"] for i in r["items"]], ["MECH_FAILURE"])
        self.assertEqual(r["items"][0]["share_pct"], 100.0)


class ProductionSummaryTests(unittest.TestCase):
    def test_totals_and_per_line(self):
        r = rm.production_summary(fixture(), D2, D2)
        # planned 100+100+50 = 250; produced 80+90+0 = 170; defective 3
        # attainment 170/250 = 68.0 ; defect rate 3/170 = 1.7647 -> 1.8 ; downtime 80 min = 1.333 h -> 1.3
        self.assertEqual(r["totals"], {
            "planned_quantity": 250, "produced_quantity": 170, "defective_quantity": 3, "good_quantity": 167,
            "attainment_pct": 68.0, "defect_rate_pct": 1.8, "downtime_minutes": 80, "downtime_hours": 1.3,
            "record_count": 3,
        })
        l02 = r["by_line"][1]
        self.assertEqual((l02["line_code"], l02["attainment_pct"], l02["defect_rate_pct"]), ("L02", 0.0, None))

    def test_run_tool_accepts_json_style_arguments(self):
        r = rm.run_tool(fixture(), "get_production_summary",
                        {"start_date": "2026-01-03", "end_date": "2026-01-03", "line_codes": ["L01"]})
        self.assertEqual(r["totals"]["produced_quantity"], 100)
        self.assertEqual(r["totals"]["downtime_minutes"], 0)


if __name__ == "__main__":
    unittest.main()
