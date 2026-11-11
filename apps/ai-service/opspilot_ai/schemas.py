"""Public contract of the AI service (docs/architecture/phase-1-plan.md §4.2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FindingKind = Literal["measurement", "calculation", "pattern", "hypothesis", "recommendation"]
ToolStatus = Literal["succeeded", "failed", "rejected", "timeout", "invalid_arguments"]


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4_000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    mode: Literal["demo", "live"] | None = None


class EvidenceRef(BaseModel):
    tool_call_id: str


class Finding(BaseModel):
    id: str
    kind: FindingKind
    text: str
    evidence: list[EvidenceRef] = []
    # How the numbers in `text` were checked against tool results.
    grounding: Literal["verified", "derived", "no_numbers"]


class ChartSeries(BaseModel):
    key: str
    label: str


class Chart(BaseModel):
    id: str
    type: Literal["bar", "line"]
    title: str
    x_key: str
    series: list[ChartSeries]
    data: list[dict[str, Any]]
    unit: str
    source_tool_call_id: str


class ToolCallRecord(BaseModel):
    id: str
    tool: str
    status: ToolStatus
    arguments: dict[str, Any]
    duration_ms: int
    result_summary: str
    error: str | None = None


class TimelineStep(BaseModel):
    step: str
    label: str
    status: Literal["succeeded", "failed", "skipped"]
    duration_ms: int


class Usage(BaseModel):
    tool_calls: int
    max_tool_calls: int
    planning_rounds: int
    input_tokens: int = 0
    output_tokens: int = 0


class ChatResponse(BaseModel):
    answer_id: str
    mode: Literal["demo", "live"]
    provider: str
    summary: str
    findings: list[Finding]
    charts: list[Chart]
    tool_calls: list[ToolCallRecord]
    timeline: list[TimelineStep]
    warnings: list[str]
    usage: Usage
