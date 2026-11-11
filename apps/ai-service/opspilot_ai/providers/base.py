"""Provider interface: the only two places a language model participates in a request.

`plan` proposes tool calls; `compose` writes the answer from the evidence. Everything else - which tools
exist, argument validation, limits, execution, grounding, charts - is deterministic code in the graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import ChatMessage, FindingKind
from ..tools import ToolResult


@dataclass
class PlannedCall:
    id: str
    tool: str
    arguments: dict


@dataclass
class PlanStep:
    calls: list[PlannedCall] = field(default_factory=list)
    # Set when the question cannot be answered with the available tools.
    unsupported: str | None = None


class DraftFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: FindingKind
    text: str = Field(max_length=600)
    evidence_tool_call_ids: list[str] = Field(default_factory=list, max_length=6)


class Draft(BaseModel):
    """The model's answer before verification. Nothing here is shown until the grounding check passes."""

    model_config = ConfigDict(extra="forbid")
    summary: str = Field(max_length=800)
    findings: list[DraftFinding] = Field(default_factory=list, max_length=8)
    chart_tool_call_ids: list[str] = Field(default_factory=list, max_length=2)


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0


class ProviderError(Exception):
    """The model call failed or was declined; the graph degrades gracefully."""


class Provider(Protocol):
    name: str
    mode: Literal["demo", "live"]
    usage: TokenUsage

    async def plan(self, history: list[ChatMessage], today: date, evidence: list[ToolResult], remaining_calls: int) -> PlanStep: ...

    async def compose(self, question: str, today: date, evidence: list[ToolResult]) -> Draft: ...
