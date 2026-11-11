"""Allowlisted analytics tools.

The AI service never touches the database. Each tool is a typed client for an internal .NET endpoint
(`POST /internal/tools/{name}`), which validates again and is authoritative (ADR 0002). Arguments are
validated here first so the model gets fast, field-level feedback.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

MAX_RANGE_DAYS = 92
LineCode = str  # validated by pattern below


class DateRangeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date = Field(description="Inclusive, plant-local (YYYY-MM-DD).")
    end_date: date = Field(description="Inclusive, plant-local (YYYY-MM-DD).")
    line_codes: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=10,
        description='Optional filter, e.g. ["L01", "L04"]. Omit for all active lines.',
    )

    @model_validator(mode="after")
    def _check(self) -> "DateRangeArgs":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days + 1 > MAX_RANGE_DAYS:
            raise ValueError(f"the range may cover at most {MAX_RANGE_DAYS} days")
        if self.line_codes is not None:
            if len(set(self.line_codes)) != len(self.line_codes):
                raise ValueError("line_codes must be unique")
            bad = [c for c in self.line_codes if not (len(c) == 3 and c[0] == "L" and c[1:].isdigit())]
            if bad:
                raise ValueError(f"line codes must look like 'L01': {bad}")
        return self


class DowntimeArgs(DateRangeArgs):
    include_planned: bool = Field(default=True, description="Include planned downtime (changeovers, planned maintenance).")
    top_n: int = Field(default=10, ge=1, le=20)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[DateRangeArgs]
    summarize: Callable[[dict[str, Any]], str]

    def input_schema(self) -> dict[str, Any]:
        """JSON schema shown to the model. Mirrors the .NET schema (checked by a contract test)."""
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
            # Pydantic renders Optional[list] as anyOf[list, null]; present it as a plain optional array.
            if "anyOf" in prop:
                variants = [v for v in prop.pop("anyOf") if v.get("type") != "null"]
                prop.update(variants[0])
                prop.pop("default", None)
        return schema


def _summ_production(d: dict[str, Any]) -> str:
    t = d["totals"]
    return f"{len(d['by_line'])} lines, {t['produced_quantity']:,} units produced, attainment {t['attainment_pct']}%"


def _summ_downtime_by_line(d: dict[str, Any]) -> str:
    return f"{len(d['items'])} lines, {d['total_downtime_minutes']:,} downtime minutes in total"


def _summ_reasons(d: dict[str, Any]) -> str:
    return f"{len(d['items'])} reasons, {d['total_downtime_minutes']:,} downtime minutes in total"


def _summ_trend(d: dict[str, Any]) -> str:
    return f"{len(d['items'])} days"


TOOLS: dict[str, ToolSpec] = {
    t.name: t
    for t in [
        ToolSpec(
            "get_production_summary",
            "Totals of planned, produced and defective units, attainment, defect rate and downtime for a date range, overall and per line. Read-only.",
            DateRangeArgs,
            _summ_production,
        ),
        ToolSpec(
            "get_downtime_by_line",
            "Downtime minutes, event count and share of total per production line for a date range, sorted by downtime descending. Read-only.",
            DowntimeArgs,
            _summ_downtime_by_line,
        ),
        ToolSpec(
            "get_downtime_reasons",
            "Downtime grouped by reason code with minutes, event count and share of total for a date range, optionally filtered by line. Read-only.",
            DowntimeArgs,
            _summ_reasons,
        ),
        ToolSpec(
            "get_daily_production_trend",
            "Per-day planned, produced and defective units, attainment, defect rate and downtime for a date range. Read-only.",
            DateRangeArgs,
            _summ_trend,
        ),
    ]
}

ResultStatus = Literal["succeeded", "failed", "rejected", "timeout", "invalid_arguments"]


@dataclass
class ToolResult:
    """One executed (or refused) tool call. This is the evidence the answer must be grounded in."""

    id: str
    tool: str
    arguments: dict[str, Any]
    status: ResultStatus
    duration_ms: int = 0
    data: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    error: str | None = None
    field_errors: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "succeeded"

    def summary(self) -> str:
        if self.ok and self.data is not None:
            return TOOLS[self.tool].summarize(self.data)
        return self.error or self.status

    def for_model(self) -> dict[str, Any]:
        """What the model sees: data only on success, a specific error otherwise. No secrets, no headers."""
        if self.ok:
            return {"tool": self.tool, "status": "ok", "data": self.data, "meta": self.meta}
        return {"tool": self.tool, "status": self.status, "error": self.error, "field_errors": self.field_errors}


def validate_arguments(tool: str, arguments: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, dict[str, list[str]]]:
    """Returns (normalized args, error, field errors). Unknown tools are refused before any I/O."""
    spec = TOOLS.get(tool)
    if spec is None:
        return None, f"Unknown tool '{tool[:64]}'. Available: {', '.join(TOOLS)}.", {}
    try:
        parsed = spec.args_model.model_validate(arguments)
    except ValidationError as e:
        fields: dict[str, list[str]] = {}
        for err in e.errors():
            key = ".".join(str(p) for p in err["loc"]) or "$"
            fields.setdefault(key, []).append(err["msg"])
        return None, "Invalid arguments.", fields
    return parsed.model_dump(mode="json", exclude_none=True), None, {}


class ToolClient:
    """Executes allowlisted tools against the .NET API. Never raises for tool-level failures."""

    SERVICE_KEY_HEADER = "X-OpsPilot-Service-Key"

    def __init__(self, base_url: str, service_key: str, timeout_s: float, transport: httpx.AsyncBaseTransport | None = None):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={self.SERVICE_KEY_HEADER: service_key, "Accept": "application/json"},
            timeout=httpx.Timeout(timeout_s, connect=min(timeout_s, 3.0)),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def today(self) -> date:
        """Plant-local "today" from the API, which applies the pinned demo clock and plant time zone."""
        r = await self._client.get("/api/meta")
        r.raise_for_status()
        return date.fromisoformat(r.json()["today"])

    async def call(self, call_id: str, tool: str, arguments: dict[str, Any]) -> ToolResult:
        started = time.perf_counter()

        def done(**kw: Any) -> ToolResult:
            return ToolResult(id=call_id, tool=tool, duration_ms=int((time.perf_counter() - started) * 1000), **kw)

        args, error, fields = validate_arguments(tool, arguments)
        if args is None:
            status: ResultStatus = "rejected" if tool not in TOOLS else "invalid_arguments"
            return done(arguments=_safe_args(arguments), status=status, error=error, field_errors=fields)

        try:
            r = await self._client.post(f"/internal/tools/{tool}", json=args)
        except httpx.TimeoutException:
            return done(arguments=args, status="timeout", error="The tool did not answer in time.")
        except httpx.HTTPError:
            return done(arguments=args, status="failed", error="The analytics API is unreachable.")

        body: dict[str, Any] = {}
        try:
            body = r.json()
        except ValueError:
            pass
        if r.status_code == 200 and body.get("status") == "ok":
            return done(arguments=args, status="succeeded", data=body["data"], meta=body.get("meta"))
        if r.status_code == 422:
            return done(arguments=args, status="invalid_arguments", error="Invalid arguments.", field_errors=body.get("errors", {}))
        if r.status_code == 504:
            return done(arguments=args, status="timeout", error="The tool query timed out.")
        if r.status_code in (401, 403, 404):
            return done(arguments=args, status="rejected", error=f"The API refused the call (HTTP {r.status_code}).")
        return done(arguments=args, status="failed", error=f"The tool failed (HTTP {r.status_code}).")


def _safe_args(arguments: Any) -> dict[str, Any]:
    """Echo rejected arguments back without trusting their size or shape."""
    if not isinstance(arguments, dict):
        return {}
    return {str(k)[:64]: (v if isinstance(v, (int, float, bool)) else str(v)[:100]) for k, v in list(arguments.items())[:10]}
