"""Charts are built from tool results by code, never from model text."""

from __future__ import annotations

from datetime import date

from .schemas import Chart, ChartSeries
from .tools import ToolResult


def _period(args: dict) -> str:
    s, e = date.fromisoformat(args["start_date"]), date.fromisoformat(args["end_date"])
    fmt = lambda d: f"{d:%b} {d.day}"  # noqa: E731
    return f"{fmt(s)}, {s.year}" if s == e else f"{fmt(s)} – {fmt(e)}, {e.year}"


def build_chart(result: ToolResult, chart_id: str) -> Chart | None:
    if not result.ok or result.data is None:
        return None
    d, period = result.data, _period(result.arguments)

    if result.tool == "get_downtime_by_line" and d["total_downtime_minutes"] > 0:
        return Chart(
            id=chart_id, type="bar", title=f"Downtime by line, {period}", x_key="line_name", unit="h",
            series=[ChartSeries(key="downtime_hours", label="Downtime (h)")],
            data=[{k: i[k] for k in ("line_code", "line_name", "downtime_hours", "downtime_minutes", "share_pct")} for i in d["items"]],
            source_tool_call_id=result.id,
        )
    if result.tool == "get_downtime_reasons" and d["items"]:
        return Chart(
            id=chart_id, type="bar", title=f"Downtime by reason, {period}", x_key="reason_name", unit="h",
            series=[ChartSeries(key="downtime_hours", label="Downtime (h)")],
            data=[{k: i[k] for k in ("reason_code", "reason_name", "is_planned", "downtime_hours", "downtime_minutes", "share_pct")} for i in d["items"]],
            source_tool_call_id=result.id,
        )
    if result.tool == "get_daily_production_trend" and len(d["items"]) > 1:
        return Chart(
            id=chart_id, type="line", title=f"Daily attainment, {period}", x_key="date", unit="%",
            series=[ChartSeries(key="attainment_pct", label="Attainment (%)")],
            data=[{k: i[k] for k in ("date", "attainment_pct", "produced_quantity", "planned_quantity", "downtime_minutes")} for i in d["items"]],
            source_tool_call_id=result.id,
        )
    if result.tool == "get_production_summary" and len(d["by_line"]) > 1:
        return Chart(
            id=chart_id, type="bar", title=f"Attainment by line, {period}", x_key="line_name", unit="%",
            series=[ChartSeries(key="attainment_pct", label="Attainment (%)")],
            data=[{k: i[k] for k in ("line_code", "line_name", "attainment_pct", "produced_quantity", "planned_quantity", "downtime_minutes")} for i in d["by_line"]],
            source_tool_call_id=result.id,
        )
    return None
