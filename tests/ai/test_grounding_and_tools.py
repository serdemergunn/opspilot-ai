import asyncio
from decimal import Decimal

import httpx
import pytest

from opspilot_ai.grounding import check_text, collect_values, extract_numbers
from opspilot_ai.tools import TOOLS, ToolClient, validate_arguments

from conftest import SERVICE_KEY

EVIDENCE = {"items": [{"downtime_minutes": 2903, "downtime_hours": 48.4, "share_pct": 40.3}], "total_downtime_minutes": 7202, "a": 83.1, "b": 79.8}


class TestGrounding:
    def test_identifiers_are_not_quantities(self):
        text = "Line 04 (L04, L04-EQ02, error E104) on Nov 4 – Nov 10, 2026 and 2026-11-10; Phase 2 adds tools."
        assert extract_numbers(text) == []

    def test_numbers_with_separators_and_units(self):
        assert [n.raw for n in extract_numbers("2,903 minutes, 48.4 h, 40.3% and −3.3 pp")] == ["2,903", "48.4", "40.3", "−3.3"]

    @pytest.mark.parametrize("text,verdict", [
        ("Line 04 recorded 2,903 minutes, 40.3% of 7,202.", "verified"),
        ("About 40% of downtime.", "verified"),  # written with less precision than the source
        ("Attainment fell by 3.3 percentage points.", "derived"),  # |83.1 - 79.8|
        ("Line 04 lost 51 hours.", "ungrounded"),
        ("Share was 40.4%.", "ungrounded"),  # off by one decimal is still wrong
        ("No numbers at all.", "no_numbers"),
    ])
    def test_check_text(self, text, verdict):
        assert check_text(text, collect_values(EVIDENCE)).verdict == verdict

    def test_measurements_can_disallow_derived_values(self):
        assert check_text("A change of 3.3.", collect_values(EVIDENCE), allow_derived=False).verdict == "ungrounded"

    def test_list_lengths_count_as_evidence(self):
        assert Decimal(1) in collect_values(EVIDENCE)


class TestToolArguments:
    def test_defaults_are_applied(self):
        args, error, _ = validate_arguments("get_downtime_by_line", {"start_date": "2026-11-04", "end_date": "2026-11-10"})
        assert error is None and args == {"start_date": "2026-11-04", "end_date": "2026-11-10", "include_planned": True, "top_n": 10}

    @pytest.mark.parametrize("args,field", [
        ({"start_date": "2026-11-10", "end_date": "2026-11-04"}, "$"),
        ({"start_date": "2026-01-01", "end_date": "2026-11-10"}, "$"),
        ({"start_date": "2026-11-04", "end_date": "2026-11-10", "top_n": 99}, "top_n"),
        ({"start_date": "2026-11-04", "end_date": "2026-11-10", "line_codes": ["Line 1"]}, "$"),
        ({"start_date": "2026-11-04", "end_date": "2026-11-10", "sql": "DROP TABLE x"}, "sql"),
        ({"start_date": "not a date", "end_date": "2026-11-10"}, "start_date"),
    ])
    def test_invalid_arguments_are_rejected_with_field_errors(self, args, field):
        parsed, error, fields = validate_arguments("get_downtime_by_line", args)
        assert parsed is None and error
        assert any(k == field or k.startswith(field) for k in fields) or field == "$"

    def test_unknown_tool(self):
        parsed, error, _ = validate_arguments("execute_sql", {"query": "SELECT 1"})
        assert parsed is None and "Unknown tool" in error

    def test_schemas_shown_to_the_model_are_strict(self):
        for spec in TOOLS.values():
            schema = spec.input_schema()
            assert schema["additionalProperties"] is False
            assert schema["required"] == ["start_date", "end_date"]
            assert schema["properties"]["line_codes"]["type"] == "array"


class TestToolClient:
    def run(self, coro):
        return asyncio.run(coro)

    def client(self, handler) -> ToolClient:
        return ToolClient("http://api.test", SERVICE_KEY, 1.0, transport=httpx.MockTransport(handler))

    def test_unknown_tool_makes_no_request(self, fake_api, tool_client):
        r = self.run(tool_client.call("tc1", "execute_sql", {"query": "DROP TABLE DowntimeEvents"}))
        assert r.status == "rejected" and fake_api.calls == []

    def test_invalid_arguments_make_no_request(self, fake_api, tool_client):
        r = self.run(tool_client.call("tc1", "get_downtime_by_line", {"start_date": "2026-11-10", "end_date": "2026-11-01"}))
        assert r.status == "invalid_arguments" and fake_api.calls == []

    def test_success_returns_data(self, tool_client):
        r = self.run(tool_client.call("tc1", "get_downtime_by_line", {"start_date": "2026-11-04", "end_date": "2026-11-10"}))
        assert r.ok and r.data["items"][0]["line_code"] == "L04"

    def test_api_422_becomes_field_errors(self, tool_client):
        r = self.run(tool_client.call("tc1", "get_downtime_by_line", {"start_date": "2026-11-04", "end_date": "2026-11-10", "line_codes": ["L99"]}))
        assert r.status == "invalid_arguments" and "line_codes" in r.field_errors

    def test_timeout(self):
        def handler(request):
            raise httpx.ReadTimeout("slow", request=request)
        r = self.run(self.client(handler).call("tc1", "get_production_summary", {"start_date": "2026-11-04", "end_date": "2026-11-10"}))
        assert r.status == "timeout"

    def test_server_error(self):
        r = self.run(self.client(lambda req: httpx.Response(500)).call("tc1", "get_production_summary", {"start_date": "2026-11-04", "end_date": "2026-11-10"}))
        assert r.status == "failed"

    def test_unreachable(self):
        def handler(request):
            raise httpx.ConnectError("refused", request=request)
        r = self.run(self.client(handler).call("tc1", "get_production_summary", {"start_date": "2026-11-04", "end_date": "2026-11-10"}))
        assert r.status == "failed" and "unreachable" in r.error
