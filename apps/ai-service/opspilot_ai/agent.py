"""The agent: one LangGraph graph with a bounded plan/execute loop.

    understand -> plan -> execute_tools -> validate_evidence -+-> respond -> ground_check -> END
                    ^                                         |
                    +---------- more evidence needed ---------+

Limits (tool calls, planning rounds, time, tokens) are enforced here, in code. The model only proposes tool
calls; the registry decides what exists and the .NET API decides what is allowed. Every number in the final
answer is checked against the tool results it cites before it is returned.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from .charts import build_chart
from .config import Mode, Settings
from .grounding import LENGTH_FIELD, check_text, collect_fields, merge
from .providers.base import Draft, PlannedCall, Provider, ProviderError
from .providers.deterministic import DeterministicProvider
from .schemas import ChatRequest, ChatResponse, EvidenceRef, Finding, TimelineStep, ToolCallRecord, Usage
from .tools import DataContext, ToolClient, ToolResult, validate_arguments

log = logging.getLogger("opspilot.agent")

COMPOSE_RESERVE_FRACTION = 0.2  # stop planning early enough to leave time for the answer
COMPOSE_RESERVE_MAX_S = 8.0


class AgentState(TypedDict, total=False):
    question: str
    data: DataContext
    evidence: list[ToolResult]
    validated: int  # number of evidence items already checked by validate_evidence
    pending: list[PlannedCall]
    rounds: int
    tool_calls_used: int
    unsupported: str | None  # system-authored refusal
    model_message: str | None  # model-authored text returned instead of tool calls
    fatal: str | None
    warnings: list[str]
    timeline: list[TimelineStep]
    draft: Draft
    system_text: bool  # the draft was written by this service, not by a provider
    response: ChatResponse


@dataclass
class _Run:
    """Per-request context shared by the graph nodes."""

    request: ChatRequest
    provider: Provider
    deadline: float
    reserve_s: float
    fell_back: bool = False

    def remaining_s(self) -> float:
        return self.deadline - time.monotonic()

    def fall_back(self) -> None:
        self.provider, self.fell_back = DeterministicProvider(), True


def _step(step: str, label: str, status: str, started: float) -> TimelineStep:
    return TimelineStep(step=step, label=label, status=status, duration_ms=int((time.monotonic() - started) * 1000))  # type: ignore[arg-type]


def _window(e: ToolResult) -> tuple[date, date] | None:
    try:
        return date.fromisoformat(e.arguments["start_date"]), date.fromisoformat(e.arguments["end_date"])
    except (KeyError, ValueError, TypeError):
        return None


def _evidence_fields(e: ToolResult) -> dict[str, set[Decimal]]:
    fields = collect_fields(e.data)
    if (w := _window(e)) is not None:  # "7 days" is a fact about the request window
        fields.setdefault(LENGTH_FIELD, set()).add(Decimal((w[1] - w[0]).days + 1))
    return fields


class Agent:
    def __init__(self, settings: Settings, tools: ToolClient, provider_factory: Callable[[Mode], Provider]):
        self.settings = settings
        self.tools = tools
        self.provider_factory = provider_factory

    async def run(self, request: ChatRequest, mode: Mode, notes: list[str] | None = None) -> ChatResponse:
        timeout = self.settings.request_timeout_s
        run = _Run(request=request, provider=self.provider_factory(mode), deadline=time.monotonic() + timeout,
                   reserve_s=min(COMPOSE_RESERVE_MAX_S, timeout * COMPOSE_RESERVE_FRACTION))
        run.provider.deadline = run.deadline
        graph = self._build(run)
        initial: AgentState = {"evidence": [], "validated": 0, "pending": [], "rounds": 0, "tool_calls_used": 0,
                               "warnings": list(notes or []), "timeline": [], "unsupported": None, "model_message": None,
                               "fatal": None}
        state = await asyncio.wait_for(graph.ainvoke(initial, {"recursion_limit": 40}), timeout=timeout + 2)
        response: ChatResponse = state["response"]
        log.info(json.dumps({
            "event": "chat_completed", "answer_id": response.answer_id, "mode": response.mode, "provider": response.provider,
            "tool_calls": [f"{t.tool}:{t.status}" for t in response.tool_calls], "findings": len(response.findings),
            "warnings": len(response.warnings), "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens,
        }))
        return response

    # ------------------------------------------------------------------------------------------------------

    def _build(self, run: _Run):  # noqa: C901 - the graph reads best in one place
        s = self.settings

        def over_budget() -> bool:
            return run.provider.usage.input_tokens + run.provider.usage.output_tokens > s.token_budget

        async def understand(state: AgentState) -> AgentState:
            t0 = time.monotonic()
            last = run.request.messages[-1]
            timeline = list(state["timeline"])
            if last.role != "user":
                return {"fatal": "The last message must come from the user.", "timeline": timeline + [_step("understand", "Request rejected", "failed", t0)]}
            if len(last.content) > s.max_question_chars:
                return {"unsupported": f"Please keep questions under {s.max_question_chars} characters.", "question": last.content,
                        "timeline": timeline + [_step("understand", "Request rejected (too long)", "failed", t0)]}
            try:
                data = await self.tools.meta()
            except Exception:  # noqa: BLE001 - any failure here means the API or its database is unavailable
                return {"fatal": "The analytics API is unavailable, so no data can be retrieved right now.", "question": last.content,
                        "timeline": timeline + [_step("understand", "Analytics API unavailable", "failed", t0)]}
            return {"question": last.content, "data": data, "timeline": timeline + [_step("understand", "Request interpreted", "succeeded", t0)]}

        async def plan(state: AgentState) -> AgentState:
            t0 = time.monotonic()
            warnings, timeline = list(state["warnings"]), list(state["timeline"])
            if run.remaining_s() < run.reserve_s:
                warnings.append("Stopped gathering evidence early to stay within the time limit.")
                return {"pending": [], "warnings": warnings}
            remaining = s.max_tool_calls - state["tool_calls_used"]
            today = state["data"].today
            try:
                step = await run.provider.plan(run.request.messages, today, state["evidence"], remaining)
            except ProviderError as e:
                if run.provider.mode == "live" and not state["evidence"]:
                    # Degrade to the deterministic provider rather than failing the request.
                    warnings.append(f"{e} This answer was produced by the deterministic demo pipeline instead.")
                    run.fall_back()
                    step = await run.provider.plan(run.request.messages, today, state["evidence"], remaining)
                else:
                    warnings.append(str(e))
                    return {"pending": [], "warnings": warnings, "timeline": timeline + [_step("plan", "Planning failed", "failed", t0)]}
            if over_budget():
                warnings.append("Token budget reached; answering with the evidence gathered so far.")
                step.calls = []
            model_message = step.message if (not step.calls and state["rounds"] == 0) else state.get("model_message")
            label = f"Planned {len(step.calls)} tool call(s)" if step.calls else ("Question not supported" if step.unsupported else "No further tools needed")
            return {
                "pending": step.calls, "rounds": state["rounds"] + 1, "unsupported": step.unsupported, "model_message": model_message,
                "warnings": warnings, "timeline": timeline + [_step("plan", label, "succeeded", t0)],
            }

        async def execute_tools(state: AgentState) -> AgentState:
            evidence, timeline = list(state["evidence"]), list(state["timeline"])
            used = state["tool_calls_used"]

            def key_of(tool: str, arguments: dict) -> tuple[str, str]:
                normalized, _, _ = validate_arguments(tool, arguments)  # compare with defaults applied
                return tool, json.dumps(normalized if normalized is not None else arguments, sort_keys=True, default=str)

            seen = {key_of(e.tool, e.arguments) for e in evidence if e.ok}
            scheduled: list[PlannedCall] = []
            refused: list[ToolResult] = []
            for call in state["pending"]:
                key = key_of(call.tool, call.arguments)
                if used + len(scheduled) >= s.max_tool_calls:
                    refused.append(ToolResult(call.id, call.tool, {}, "rejected", error=f"Tool call limit reached ({s.max_tool_calls} per request)."))
                elif key in seen:
                    refused.append(ToolResult(call.id, call.tool, call.arguments, "rejected", error="Duplicate of a call that already succeeded; reuse that result."))
                else:
                    seen.add(key)
                    scheduled.append(call)
            results = await asyncio.gather(*(self.tools.call(c.id, c.tool, c.arguments) for c in scheduled))
            for r in [*results, *refused]:
                evidence.append(r)
                timeline.append(TimelineStep(step="tool", label=f"{r.tool} {r.status.replace('_', ' ')}",
                                             status="succeeded" if r.ok else ("skipped" if r.status == "rejected" else "failed"), duration_ms=r.duration_ms))
            return {"evidence": evidence, "pending": [], "tool_calls_used": used + len(scheduled), "timeline": timeline}

        async def validate_evidence(state: AgentState) -> AgentState:
            t0 = time.monotonic()
            warnings, data = list(state["warnings"]), state["data"]
            for e in state["evidence"][state["validated"]:]:
                if not e.ok:
                    continue
                d, window = e.data or {}, _window(e)
                if window is not None:
                    e.coverage = data.coverage(*window)
                    if e.coverage != "full":
                        span = f"{data.first_date} to {data.last_date}" if data.first_date else "no dates"
                        what = "No records exist for" if e.coverage == "none" else "Records cover only part of"
                        warnings.append(f"{what} {window[0]} to {window[1]} ({e.tool}); the dataset covers {span}.")
                if e.coverage != "none":
                    if e.tool in ("get_downtime_by_line", "get_downtime_reasons") and d.get("total_downtime_minutes") == 0:
                        warnings.append(f"{e.tool} found no downtime for {e.arguments['start_date']} to {e.arguments['end_date']}.")
                    if e.tool == "get_production_summary" and sum(row["produced_quantity"] for row in d["by_line"]) != d["totals"]["produced_quantity"]:
                        warnings.append("Contradictory data: per-line production does not add up to the reported total.")
            ok = sum(e.ok for e in state["evidence"])
            label = f"Results validated ({ok} succeeded, {len(state['evidence']) - ok} not used)"
            return {"warnings": warnings, "validated": len(state["evidence"]),
                    "timeline": state["timeline"] + [_step("validate", label, "succeeded", t0)]}

        async def respond(state: AgentState) -> AgentState:
            t0 = time.monotonic()
            warnings, evidence = list(state["warnings"]), state["evidence"]
            today = state["data"].today if state.get("data") else date.today()
            system_text = True
            if state.get("fatal"):
                draft = Draft(summary=state["fatal"])
            elif state.get("unsupported"):
                draft = Draft(summary=state["unsupported"])
            elif not any(e.ok for e in evidence):
                if state.get("model_message") and not evidence:
                    draft, system_text = Draft(summary=state["model_message"][:800]), False
                else:
                    problems = "; ".join(sorted({f"{e.tool}: {e.error or e.status}" for e in evidence})) or "no tool was called"
                    draft = Draft(summary=f"I could not retrieve the data needed to answer ({problems}).")
            else:
                system_text = False
                use_model = run.provider.mode == "live" and not run.fell_back
                if use_model and over_budget():
                    warnings.append("Token budget reached before the answer was written; the findings come from the deterministic demo pipeline.")
                    use_model = False
                elif use_model and run.remaining_s() < run.reserve_s / 2:
                    warnings.append("Not enough time left to ask the model for the answer; the findings come from the deterministic demo pipeline.")
                    use_model = False
                draft = None
                if use_model or run.provider.mode == "demo":
                    try:
                        draft = await run.provider.compose(state["question"], today, evidence)
                    except ProviderError as e:
                        warnings.append(f"{e} The findings below were produced by the deterministic demo pipeline from the same tool results.")
                if draft is None:
                    run.fell_back = run.fell_back or run.provider.mode == "live"
                    draft = await DeterministicProvider().compose(state["question"], today, evidence)
            return {"draft": draft, "system_text": system_text, "warnings": warnings,
                    "timeline": state["timeline"] + [_step("respond", "Answer composed", "succeeded", t0)]}

        async def ground_check(state: AgentState) -> AgentState:
            t0 = time.monotonic()
            draft, evidence, warnings = state["draft"], state["evidence"], list(state["warnings"])
            ok = {e.id: e for e in evidence if e.ok}
            fields_by_id = {i: _evidence_fields(e) for i, e in ok.items()}
            all_fields = merge(*fields_by_id.values())

            findings: list[Finding] = []
            for f in draft.findings:
                refs = list(dict.fromkeys(i for i in f.evidence_tool_call_ids if i in ok))
                fields = merge(*(fields_by_id[i] for i in refs))  # numbers must come from the cited results
                result = check_text(f.text, fields, allow_derived=f.kind != "measurement")
                if result.verdict == "ungrounded":
                    reason = (f"its numbers ({', '.join(result.ungrounded)}) do not appear in the cited tool results"
                              if refs else "it contains numbers but cites no tool result")
                    warnings.append(f"Removed a {f.kind} statement because {reason}.")
                    continue
                findings.append(Finding(id=f"f{len(findings) + 1}", kind=f.kind, text=f.text,
                                        evidence=[EvidenceRef(tool_call_id=i) for i in refs], grounding=result.verdict))  # type: ignore[arg-type]

            summary = draft.summary
            if not state.get("system_text") and check_text(summary, all_fields).verdict == "ungrounded":
                summary = "The summary was withheld because it contained numbers that could not be verified against the tool results. The verified findings are listed below."
                warnings.append("Withheld an unverifiable summary.")

            charts = []
            chartable = [i for i in ok if ok[i].coverage != "none"]
            chart_ids = [i for i in draft.chart_tool_call_ids if i in chartable] or chartable
            for i in chart_ids:
                chart = build_chart(ok[i], f"c{len(charts) + 1}")
                if chart:
                    charts.append(chart)
                if len(charts) == 2:
                    break

            verified = sum(f.grounding in ("verified", "derived") for f in findings)
            timeline = state["timeline"] + [_step("ground", f"Numbers checked ({verified} of {len(findings)} findings contain verified numbers)", "succeeded", t0)]
            provider = run.provider
            response = ChatResponse(
                answer_id=f"ans_{uuid.uuid4().hex[:16]}",
                mode="demo" if (provider.mode == "demo" or run.fell_back) else "live",
                provider=provider.name + (" (fallback: deterministic)" if run.fell_back and provider.mode == "live" else ""),
                summary=summary,
                findings=findings,
                charts=charts,
                tool_calls=[ToolCallRecord(id=e.id, tool=e.tool, status=e.status, arguments=e.arguments, duration_ms=e.duration_ms,
                                           result_summary=e.summary(), error=e.error) for e in evidence],
                timeline=timeline,
                warnings=warnings,
                usage=Usage(tool_calls=state["tool_calls_used"], max_tool_calls=s.max_tool_calls, planning_rounds=state["rounds"],
                            input_tokens=provider.usage.input_tokens, output_tokens=provider.usage.output_tokens),
            )
            return {"response": response, "timeline": timeline}

        def after_understand(state: AgentState) -> str:
            return "respond" if state.get("fatal") or state.get("unsupported") else "plan"

        def after_plan(state: AgentState) -> str:
            return "execute_tools" if state["pending"] else "respond"

        def after_validate(state: AgentState) -> str:
            more_allowed = state["rounds"] < s.max_planning_rounds and state["tool_calls_used"] < s.max_tool_calls
            return "plan" if more_allowed and run.remaining_s() > run.reserve_s else "respond"

        g = StateGraph(AgentState)
        for name, fn in [("understand", understand), ("plan", plan), ("execute_tools", execute_tools),
                         ("validate_evidence", validate_evidence), ("respond", respond), ("ground_check", ground_check)]:
            g.add_node(name, fn)
        g.add_edge(START, "understand")
        g.add_conditional_edges("understand", after_understand, {"plan": "plan", "respond": "respond"})
        g.add_conditional_edges("plan", after_plan, {"execute_tools": "execute_tools", "respond": "respond"})
        g.add_edge("execute_tools", "validate_evidence")
        g.add_conditional_edges("validate_evidence", after_validate, {"plan": "plan", "respond": "respond"})
        g.add_edge("respond", "ground_check")
        g.add_edge("ground_check", END)
        return g.compile()
