"""Demo mode: rule-based planning and template answers, no LLM.

It runs through the same graph as the live provider: the same tools are called against the same data, and
the same grounding check verifies every number. Responses are labeled `mode: "demo"` so they are never
mistaken for model output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from ..schemas import ChatMessage
from ..tools import ToolResult
from .base import Draft, DraftFinding, PlanStep, PlannedCall, TokenUsage

Intent = Literal["compare", "why_drop", "reasons", "downtime_by_line", "summary", "trend", "production"]

_WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10}


@dataclass
class Period:
    start: date
    end: date

    @property
    def label(self) -> str:
        fmt = lambda d: f"{d:%b} {d.day}"  # noqa: E731
        return f"{fmt(self.start)}, {self.start.year}" if self.start == self.end else f"{fmt(self.start)} – {fmt(self.end)}, {self.end.year}"

    def previous(self) -> "Period":
        days = (self.end - self.start).days + 1
        return Period(self.start - timedelta(days=days), self.start - timedelta(days=1))

    def args(self) -> dict[str, str]:
        return {"start_date": self.start.isoformat(), "end_date": self.end.isoformat()}


@dataclass
class Interpretation:
    intent: Intent | None
    period: Period
    lines: list[str]
    top_n: int | None
    unsupported: str | None = None


UNSUPPORTED_QUALITY = (
    "Quality incident analysis (categories, severity, status) arrives with the get_quality_issues tool in Phase 2. "
    "Today I can report defect rates from production records, for example: \"What was the defect rate last week?\""
)
UNSUPPORTED_DOCS = (
    "Equipment, maintenance and documentation questions (such as error codes) need tools that arrive in Phase 2 "
    "(equipment incidents) and Phase 3 (knowledge base search). Today I can answer production and downtime questions."
)
UNSUPPORTED_INSTRUCTIONS = (
    "I only answer operational questions with read-only analytics tools. I cannot run SQL, change my instructions "
    "or reveal configuration."
)
UNSUPPORTED_GENERIC = (
    "I can answer questions about production volume, attainment, defect rate and downtime by line or by reason, "
    "for periods of up to 92 days. This question is outside what the available tools cover."
)


UNSUPPORTED_FORECAST = (
    "OpsPilot reports on recorded data only; it does not forecast future periods. "
    "Ask about a past period, for example \"last week\" or \"October 2026\"."
)
UNSUPPORTED_PERIOD = (
    "I could not tell which period you mean. Use a relative period (\"yesterday\", \"last 7 days\", \"last 3 weeks\", "
    "\"last month\"), a month (\"October 2026\") or dates (\"from 2026-10-01 to 2026-10-07\")."
)
UNSUPPORTED_RANGE = "Periods can cover at most 92 days. Please ask about a shorter period."

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], start=1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_MONTHS["sept"] = 9
_COUNT = r"(\d{1,2}|" + "|".join(_WORD_NUMBERS) + r")"


def _count(token: str) -> int:
    return _WORD_NUMBERS.get(token) or int(token)


def _month_period(month: int, year: int | None, today: date) -> Period:
    if year is None:  # the most recent such month that has started
        year = today.year if month <= today.month else today.year - 1
    start = date(year, month, 1)
    end = (date(year + month // 12, month % 12 + 1, 1)) - timedelta(days=1)
    return Period(start, min(end, today - timedelta(days=1)) if end >= today else end)


def parse_period(q: str, today: date) -> tuple[Period | None, str | None]:
    """Returns (period, problem). Never substitutes a default for a period the user did ask about."""
    yesterday = today - timedelta(days=1)
    last_n = lambda days: Period(yesterday - timedelta(days=days - 1), yesterday)  # noqa: E731

    if re.search(r"\b(?:next|tomorrow|upcoming|will|forecast|predict|projected?)\b", q):
        return None, UNSUPPORTED_FORECAST
    dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", q)
    if dates:
        try:
            parsed = sorted(date.fromisoformat(d) for d in dates[:2])
        except ValueError:
            return None, UNSUPPORTED_PERIOD
        period = Period(parsed[0], parsed[-1])
    elif "yesterday" in q:
        period = Period(yesterday, yesterday)
    elif m := re.search(rf"\b(?:last|past|previous)\s+{_COUNT}\s+days?\b", q):
        period = last_n(_count(m.group(1)))
    elif m := re.search(rf"\b(?:last|past|previous)\s+{_COUNT}\s+weeks?\b", q):
        period = last_n(7 * _count(m.group(1)))
    elif m := re.search(rf"\b(?:last|past|previous)\s+{_COUNT}\s+months?\b", q):
        months = _count(m.group(1))
        first_this = today.replace(day=1)
        start = first_this
        for _ in range(months):
            start = (start - timedelta(days=1)).replace(day=1)
        period = Period(start, first_this - timedelta(days=1))
    elif re.search(r"\b(?:last|previous|past)\s+month\b", q):
        last_prev = today.replace(day=1) - timedelta(days=1)
        period = Period(last_prev.replace(day=1), last_prev)
    elif re.search(r"\bthis\s+month\b|\bmonth[-\s]to[-\s]date\b", q):
        period = Period(today.replace(day=1), yesterday) if today.day > 1 else last_n(1)
    elif re.search(r"\b(?:last|past|previous)\s+quarter\b", q):
        period = last_n(90)
    elif m := re.search(
        r"\b(?:(?:in|during|for|of)\s+)?(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\b(?:\s+(\d{4}))?", q
    ):
        name, year = m.group(1), m.group(2)
        # "may" is also a verb: only read it as a month with "in/during/for/of" before it or a year after it.
        if name == "may" and not (year or re.search(r"\b(?:in|during|for|of)\s+may\b", q)):
            period = last_n(7)
        else:
            period = _month_period(_MONTHS[name], int(year) if year else None, today)
    elif re.search(r"\b(?:19|20)\d{2}\b|\bq[1-4]\b|\bquarter\b|\bsince\b|\bweek of\b", q):
        return None, UNSUPPORTED_PERIOD  # a period was given but not in a form we understand
    else:
        # "last week", "this week" or no period at all: the last 7 complete days.
        period = last_n(7)

    if period.start >= today:
        return None, UNSUPPORTED_FORECAST
    if (period.end - period.start).days + 1 > 92:
        return None, UNSUPPORTED_RANGE
    return period, None


def parse_lines(q: str) -> list[str]:
    codes: list[str] = []

    def add(num: str) -> None:
        code = f"L{int(num):02d}"
        if code not in codes:
            codes.append(code)

    # "line 4", "lines 4 and 5", "lines 1, 2 and 4", "L04"
    for m in re.finditer(r"\blines?\s*((?:0?\d{1,2})(?:\s*(?:,|and|&|vs\.?|versus)\s*(?:line\s*)?0?\d{1,2})*)\b", q):
        for num in re.findall(r"\d{1,2}", m.group(1)):
            add(num)
    for m in re.finditer(r"\bl(\d{2})\b", q):
        add(m.group(1))
    return codes


def parse_top_n(q: str) -> int | None:
    if m := re.search(r"\btop\s+(\d{1,2})\b", q):
        return max(1, min(20, int(m.group(1))))
    if m := re.search(r"\b(?:top\s+|the\s+)?(" + "|".join(_WORD_NUMBERS) + r")\s+(?:most|largest|biggest|main|common|top)", q):
        return _WORD_NUMBERS[m.group(1)]
    return None


def interpret(question: str, today: date) -> Interpretation:
    q = question.lower()
    parsed_period, period_problem = parse_period(q, today)
    period = parsed_period or Period(today - timedelta(days=7), today - timedelta(days=1))
    lines, top_n = parse_lines(q), parse_top_n(q)

    def result(intent: Intent | None, unsupported: str | None = None) -> Interpretation:
        return Interpretation(intent, period, lines, top_n, unsupported)

    # Requests to run code or override instructions are declined outright, whatever else they mention.
    if re.search(r"\b(?:drop|truncate|alter)\s+table\b|\bdelete\s+from\b|\binsert\s+into\b|\bupdate\s+\w+\s+set\b|\bselect\s+(?:\*|[\w,\s]+?)\s+from\s+\w+\s*(?:;|$|where)|;\s*--|"
                 r"ignore (?:all |any |the )?(?:previous |prior |above )?(?:instructions|rules)|system prompt|developer mode", q):
        return result(None, UNSUPPORTED_INSTRUCTIONS)
    if re.search(r"quality (?:issue|incident|problem)|incident categor|severity", q):
        return result(None, UNSUPPORTED_QUALITY)
    if re.search(r"error code|\be\d{3}\b|maintenance|documentation|manual|procedure|troubleshoot|equipment", q):
        return result(None, UNSUPPORTED_DOCS)
    if period_problem:
        return result(None, period_problem)

    downtime = re.search(r"downtime|interruption|stoppage|stops?\b|outage", q)
    if (re.search(r"\bcompare\b|\bvs\.?\b|versus", q)) and len(lines) >= 2:
        return result("compare")
    if re.search(r"\bwhy\b|decreas|drop|declin|fell|lower|worse", q) and re.search(r"efficien|attainment|output|production|performance", q):
        return result("why_drop")
    if downtime and re.search(r"reason|cause|why", q):
        return result("reasons")
    if downtime:
        return result("downtime_by_line")
    if re.search(r"summar|overview|performance|how did", q):
        return result("summary")
    if re.search(r"trend|daily|per day|each day", q):
        return result("trend")
    if re.search(r"production|produced|output|attainment|efficien|defect|scrap|units", q):
        return result("production")
    return result(None, UNSUPPORTED_GENERIC)


# ---------------------------------------------------------------------------------------------------------
# Formatting: numbers are copied from tool results unchanged (the API already rounded them).
# ---------------------------------------------------------------------------------------------------------

def n(v: int) -> str:
    return f"{v:,}"


def pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v}%"


def diff_1dp(a: float, b: float) -> str:
    return str(abs(Decimal(str(a)) - Decimal(str(b))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


class DeterministicProvider:
    name = "deterministic"
    mode: Literal["demo", "live"] = "demo"

    def __init__(self) -> None:
        self.usage = TokenUsage()
        self.deadline: float | None = None
        self._planned = False

    async def plan(self, history: list[ChatMessage], today: date, evidence: list[ToolResult], remaining_calls: int) -> PlanStep:
        if self._planned:  # one planning round: the rules already know everything they will need
            return PlanStep()
        self._planned = True
        i = interpret(history[-1].content, today)
        if i.unsupported:
            return PlanStep(unsupported=i.unsupported)

        p, lines = i.period.args(), ({"line_codes": i.lines} if i.lines else {})
        calls: list[tuple[str, dict[str, Any]]] = []
        match i.intent:
            case "compare":
                calls = [("get_production_summary", {**p, **lines}), ("get_downtime_by_line", {**p, **lines})]
            case "why_drop":
                prev = i.period.previous().args()
                calls = [
                    ("get_production_summary", {**p, **lines}),
                    ("get_production_summary", {**prev, **lines}),
                    ("get_downtime_by_line", {**p, **lines}),
                    ("get_downtime_reasons", {**p, **lines, "top_n": 5}),
                ]
            case "reasons":
                calls = [("get_downtime_reasons", {**p, **lines, **({"top_n": i.top_n} if i.top_n else {})})]
            case "downtime_by_line":
                calls = [("get_downtime_by_line", {**p, **lines})]
            case "summary":
                calls = [("get_production_summary", {**p, **lines}), ("get_daily_production_trend", {**p, **lines}), ("get_downtime_by_line", {**p, **lines})]
            case "trend":
                calls = [("get_daily_production_trend", {**p, **lines})]
            case "production":
                calls = [("get_production_summary", {**p, **lines})]
        return PlanStep(calls=[PlannedCall(id=f"tc{k}", tool=t, arguments=a) for k, (t, a) in enumerate(calls[:remaining_calls], start=1)])

    async def compose(self, question: str, today: date, evidence: list[ToolResult]) -> Draft:
        i = interpret(question, today)
        ok = [e for e in evidence if e.ok]
        if ok and all(e.coverage == "none" for e in ok):
            # Zeros from a window without records mean "no data", never "nothing happened".
            return Draft(summary=f"No data is available for {i.period.label}: the dataset has no records for that period, "
                                 "so no figures can be reported.")
        by_tool: dict[str, list[ToolResult]] = {}
        for e in ok:
            by_tool.setdefault(e.tool, []).append(e)
        writer = _Writer(i, by_tool)
        match i.intent:
            case "compare":
                writer.compare()
            case "why_drop":
                writer.why_drop()
            case "reasons":
                writer.reasons()
            case "downtime_by_line":
                writer.downtime_by_line()
            case "summary":
                writer.summary_report()
            case "trend":
                writer.trend()
            case _:
                writer.production()
        return writer.draft()


class _Writer:
    def __init__(self, i: Interpretation, by_tool: dict[str, list[ToolResult]]):
        self.i, self.by_tool = i, by_tool
        self.summary = ""
        self.findings: list[DraftFinding] = []
        self.charts: list[str] = []

    def first(self, tool: str, index: int = 0) -> ToolResult | None:
        results = self.by_tool.get(tool, [])
        return results[index] if len(results) > index else None

    def add(self, kind: str, text: str, *sources: ToolResult) -> None:
        self.findings.append(DraftFinding(kind=kind, text=text, evidence_tool_call_ids=[s.id for s in sources]))  # type: ignore[arg-type]

    def draft(self) -> Draft:
        summary = self.summary or "The requested data could not be retrieved, so no answer can be given."
        return Draft(summary=summary, findings=self.findings[:8], chart_tool_call_ids=self.charts[:2])

    @property
    def scope(self) -> str:
        return f" on {', '.join('Line ' + c[1:] for c in self.i.lines)}" if self.i.lines else ""

    # -- intents ------------------------------------------------------------------------------------------

    def downtime_by_line(self) -> None:
        r = self.first("get_downtime_by_line")
        if not r:
            return
        d, period = r.data, self.i.period.label
        items = d["items"]
        if d["total_downtime_minutes"] == 0:
            self.summary = f"No downtime was recorded{self.scope} for {period}."
            self.add("measurement", f"The downtime records contain 0 minutes of downtime{self.scope} for {period}.", r)
            return
        top = items[0]
        self.charts.append(r.id)
        self.summary = (
            f"{top['line_name']} had the most downtime for {period}: {top['downtime_hours']} h "
            f"({n(top['downtime_minutes'])} minutes), {pct(top['share_pct'])} of the total."
        )
        self.add("calculation", f"{top['line_name']} recorded {n(top['downtime_minutes'])} minutes of downtime, {pct(top['share_pct'])} of the {n(d['total_downtime_minutes'])} minutes recorded across {len(items)} lines.", r)
        self.add("measurement", f"{top['line_name']} had {top['event_count']} downtime events in the period.", r)
        if len(items) > 1:
            s = items[1]
            self.add("measurement", f"{s['line_name']} followed with {n(s['downtime_minutes'])} minutes ({pct(s['share_pct'])}).", r)
        self.add("hypothesis", f"Downtime is concentrated on {top['line_name']}, which points to a line-specific cause rather than a plant-wide one. The reason breakdown for that line would test this.")
        self.add("recommendation", f"Ask for the downtime reasons on {top['line_name']} for the same period to see what drives it.")

    def reasons(self) -> None:
        r = self.first("get_downtime_reasons")
        if not r:
            return
        d, period = r.data, self.i.period.label
        items = d["items"]
        if not items:
            self.summary = f"No downtime was recorded{self.scope} for {period}."
            self.add("measurement", f"The downtime records contain 0 minutes of downtime{self.scope} for {period}.", r)
            return
        self.charts.append(r.id)
        top = items[0]
        self.summary = f"{top['reason_name']} was the largest cause of downtime{self.scope} for {period}: {top['downtime_hours']} h, {pct(top['share_pct'])} of the total."
        for item in items[: (self.i.top_n or 3)]:
            kind = "planned" if item["is_planned"] else "unplanned"
            self.add("calculation", f"{item['reason_name']} ({kind}): {n(item['downtime_minutes'])} minutes across {item['event_count']} events, {pct(item['share_pct'])} of downtime.", r)
        if top["reason_code"] in ("MECH_FAILURE", "ELEC_FAULT"):
            self.add("hypothesis", "Recurring equipment faults may be driving these stoppages. Equipment and maintenance records (Phase 2 tools) are needed to confirm a cause.")
        self.add("recommendation", f"Investigate {top['reason_name'].lower()} events{self.scope} first; they account for the largest share of lost time.")

    def compare(self) -> None:
        s, dl = self.first("get_production_summary"), self.first("get_downtime_by_line")
        if not s:
            return
        rows = s.data["by_line"]
        self.charts.append(s.id)
        for row in rows:
            self.add("measurement", f"{row['line_name']}: {n(row['produced_quantity'])} of {n(row['planned_quantity'])} planned units ({pct(row['attainment_pct'])} attainment) and {n(row['downtime_minutes'])} minutes of downtime.", s)
        if len(rows) >= 2 and all(r["attainment_pct"] is not None for r in rows[:2]):
            a, b = sorted(rows[:2], key=lambda r: r["attainment_pct"], reverse=True)
            self.summary = f"{a['line_name']} outperformed {b['line_name']} for {self.i.period.label}: {pct(a['attainment_pct'])} versus {pct(b['attainment_pct'])} attainment."
            self.add("calculation", f"{a['line_name']}'s attainment was {diff_1dp(a['attainment_pct'], b['attainment_pct'])} percentage points higher than {b['line_name']}'s.", s)
            if b["downtime_minutes"] > a["downtime_minutes"]:
                self.add("hypothesis", f"{b['line_name']}'s lower attainment coincides with more downtime, which is the most likely main contributor. Rate losses while running could also play a part.")
                self.add("recommendation", f"Review the downtime reasons for {b['line_name']} in the same period.")
        if dl:
            self.charts.append(dl.id)

    def why_drop(self) -> None:
        cur, prev = self.first("get_production_summary", 0), self.first("get_production_summary", 1)
        dl, rs = self.first("get_downtime_by_line"), self.first("get_downtime_reasons")
        period, prev_period = self.i.period.label, self.i.period.previous().label
        if cur and prev:
            c, p = cur.data["totals"], prev.data["totals"]
            if c["attainment_pct"] is not None and p["attainment_pct"] is not None:
                fell = c["attainment_pct"] < p["attainment_pct"]
                change = diff_1dp(c["attainment_pct"], p["attainment_pct"])
                self.summary = (
                    f"Attainment fell from {pct(p['attainment_pct'])} to {pct(c['attainment_pct'])} ({change} percentage points) for {period} compared with {prev_period}."
                    if fell
                    else f"Attainment did not decrease for {period}: {pct(c['attainment_pct'])}, compared with {pct(p['attainment_pct'])} for {prev_period}."
                )
                self.add("calculation", f"Attainment was {pct(c['attainment_pct'])} for {period} and {pct(p['attainment_pct'])} for {prev_period}, a change of {change} percentage points.", cur, prev)
            self.add("measurement", f"Downtime totalled {n(c['downtime_minutes'])} minutes for {period}, against {n(p['downtime_minutes'])} minutes for {prev_period}.", cur, prev)
        if dl and dl.data["total_downtime_minutes"] > 0:
            top = dl.data["items"][0]
            self.charts.append(dl.id)
            self.add("pattern", f"{top['line_name']} contributed the most downtime for {period}: {n(top['downtime_minutes'])} minutes, {pct(top['share_pct'])} of the total.", dl)
            if rs and rs.data["items"]:
                r1 = rs.data["items"][0]
                self.add("pattern", f"The leading downtime reason was {r1['reason_name'].lower()} at {pct(r1['share_pct'])} of downtime minutes.", rs)
                self.add("hypothesis", f"Downtime on {top['line_name']}, mainly {r1['reason_name'].lower()}, is the most likely driver of the lower output. The data shows the two coincide; it does not prove causation.")
            self.add("recommendation", f"Start the investigation on {top['line_name']} and compare its event log with the previous period.")

    def summary_report(self) -> None:
        s, t, dl = self.first("get_production_summary"), self.first("get_daily_production_trend"), self.first("get_downtime_by_line")
        if s:
            tot = s.data["totals"]
            self.summary = (
                f"For {self.i.period.label}{self.scope} the plant produced {n(tot['produced_quantity'])} units against {n(tot['planned_quantity'])} planned "
                f"({pct(tot['attainment_pct'])} attainment), with {tot['downtime_hours']} h of downtime."
            )
            self.add("measurement", f"{n(tot['produced_quantity'])} units were produced against {n(tot['planned_quantity'])} planned, an attainment of {pct(tot['attainment_pct'])}.", s)
            self.add("measurement", f"{n(tot['defective_quantity'])} units were defective, a defect rate of {pct(tot['defect_rate_pct'])}.", s)
        if t:
            self._trend_findings(t)
            self.charts.append(t.id)
        if dl and dl.data["total_downtime_minutes"] > 0:
            top = dl.data["items"][0]
            self.add("calculation", f"{top['line_name']} accounted for the largest share of downtime: {n(top['downtime_minutes'])} minutes, {pct(top['share_pct'])}.", dl)
            self.add("recommendation", f"Review downtime reasons on {top['line_name']}, the largest contributor.")

    def trend(self) -> None:
        t = self.first("get_daily_production_trend")
        if t:
            self.charts.append(t.id)
            self._trend_findings(t)
            if not self.summary:
                self.summary = f"Daily attainment for {self.i.period.label}{self.scope} is shown below."

    def production(self) -> None:
        s = self.first("get_production_summary")
        if not s:
            return
        tot = s.data["totals"]
        self.summary = f"For {self.i.period.label}{self.scope}: {n(tot['produced_quantity'])} units produced against {n(tot['planned_quantity'])} planned ({pct(tot['attainment_pct'])} attainment), defect rate {pct(tot['defect_rate_pct'])}."
        self.add("measurement", f"{n(tot['produced_quantity'])} of {n(tot['planned_quantity'])} planned units were produced ({pct(tot['attainment_pct'])} attainment).", s)
        self.add("measurement", f"{n(tot['defective_quantity'])} units were defective, a defect rate of {pct(tot['defect_rate_pct'])}.", s)
        if len(s.data["by_line"]) > 1:
            self.charts.append(s.id)

    def _trend_findings(self, t: ToolResult) -> None:
        days = [d for d in t.data["items"] if d["attainment_pct"] is not None]
        if len(days) < 2:
            return
        lo, hi = min(days, key=lambda d: d["attainment_pct"]), max(days, key=lambda d: d["attainment_pct"])
        fmt = lambda iso: f"{date.fromisoformat(iso):%b} {date.fromisoformat(iso).day}"  # noqa: E731
        self.add("pattern", f"Daily attainment ranged from {pct(lo['attainment_pct'])} on {fmt(lo['date'])} to {pct(hi['attainment_pct'])} on {fmt(hi['date'])}.", t)
        if not self.summary:
            self.summary = f"Daily attainment ranged from {pct(lo['attainment_pct'])} to {pct(hi['attainment_pct'])} for {self.i.period.label}{self.scope}."
