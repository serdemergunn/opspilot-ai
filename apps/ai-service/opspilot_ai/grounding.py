"""Number grounding: every number in an answer must come from a tool result.

This is a deterministic check, independent of the model. A number is accepted when it equals a value in the
cited tool results at the precision it is written with ("verified"), or - except for measurements - the absolute
difference of two values of the *same field* in those results ("derived", e.g. attainment 83.1% vs 79.8%
-> 3.3 points). Anything else is treated as fabricated and the statement is removed.

Identifiers are not quantities and are ignored: dates, line names ("Line 04", "L04"), error codes ("E104"),
equipment codes and roadmap references ("Phase 2"). Month names are matched case-sensitively and as whole
words, so ordinary words such as "declined" or "may" never hide a number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from itertools import combinations
from typing import Any, Literal, Mapping

_MONTH = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?"
)
_DAY = r"(?:3[01]|[12]\d|0?[1-9])(?:st|nd|rd|th)?(?![\d.,]\d)"
_IDENTIFIERS = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),  # 2026-11-10
    re.compile(rf"\b{_MONTH}\s+{_DAY}(?:,?\s+\d{{4}})?\b"),  # Nov 4, 2026 / Nov 4
    re.compile(rf"\b{_DAY}\s+{_MONTH}(?:\s+\d{{4}})?\b"),  # 4 Nov 2026
    re.compile(rf"\b{_MONTH}\s+\d{{4}}\b"),  # October 2026
    re.compile(r"\b(?:production\s+)?[Ll]ines?\s+0?\d{1,2}\b"),  # Line 04
    re.compile(r"\bL\d{2}\b"),  # L04
    re.compile(r"\b[A-Z]\d{2}-EQ\d{2}\b"),  # L04-EQ02
    re.compile(r"\b[A-Z]\d{3}\b"),  # E104
    re.compile(r"\b(?:[Pp]hase|[Mm]ilestone)\s+\d+\b"),  # Phase 2
]
_NUMBER = re.compile(r"(?<![\w.])[-−+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w])")

LENGTH_FIELD = "__len__"  # list lengths, e.g. "across 6 lines"
# Differences are only accepted within small fields: two periods' totals, or up to six lines compared side by
# side. Long per-day series would make almost any integer reachable as a difference.
MAX_DERIVED_POOL = 6
Fields = Mapping[str, set[Decimal]]


@dataclass(frozen=True)
class Number:
    raw: str
    value: Decimal  # absolute value; direction is carried by words ("fell", "higher")
    decimals: int


def extract_numbers(text: str) -> list[Number]:
    for pattern in _IDENTIFIERS:
        text = pattern.sub(" ", text)
    out: list[Number] = []
    for m in _NUMBER.finditer(text):
        raw = m.group(0)
        cleaned = raw.replace(",", "").replace("−", "-").lstrip("+-")
        try:
            value = Decimal(cleaned)
        except InvalidOperation:
            continue
        decimals = len(cleaned.split(".")[1]) if "." in cleaned else 0
        out.append(Number(raw=raw, value=value, decimals=decimals))
    return out


def collect_fields(obj: Any, into: dict[str, set[Decimal]] | None = None) -> dict[str, set[Decimal]]:
    """Numeric leaves of a tool result grouped by field path ("totals.attainment_pct", "items[].share_pct"),
    plus list lengths. The same path from two results of the same tool lands in the same group."""
    fields = into if into is not None else {}

    def walk(o: Any, path: str) -> None:
        if isinstance(o, bool) or o is None:
            return
        if isinstance(o, (int, float)):
            fields.setdefault(path, set()).add(abs(Decimal(str(o))))
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(o, list):
            fields.setdefault(LENGTH_FIELD, set()).add(Decimal(len(o)))
            for v in o:
                walk(v, f"{path}[]")

    walk(obj, "")
    return fields


def merge(*parts: Fields) -> dict[str, set[Decimal]]:
    out: dict[str, set[Decimal]] = {}
    for p in parts:
        for k, v in p.items():
            out.setdefault(k, set()).update(v)
    return out


def _round(v: Decimal, decimals: int) -> Decimal:
    return v.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


Verdict = Literal["verified", "derived", "no_numbers", "ungrounded"]


@dataclass
class CheckResult:
    verdict: Verdict
    ungrounded: list[str]


def check_text(text: str, fields: Fields, allow_derived: bool = True) -> CheckResult:
    numbers = extract_numbers(text)
    if not numbers:
        return CheckResult("no_numbers", [])
    values = set().union(*fields.values()) if fields else set()
    differences: set[Decimal] | None = None
    derived_used = False
    ungrounded: list[str] = []
    for n in numbers:
        if any(_round(v, n.decimals) == n.value for v in values):
            continue
        if allow_derived:
            if differences is None:
                differences = {
                    abs(a - b)
                    for name, vs in fields.items() if name != LENGTH_FIELD and len(vs) <= MAX_DERIVED_POOL
                    for a, b in combinations(sorted(vs), 2)
                }
            if any(_round(d, n.decimals) == n.value for d in differences):
                derived_used = True
                continue
        ungrounded.append(n.raw)
    if ungrounded:
        return CheckResult("ungrounded", ungrounded)
    return CheckResult("derived" if derived_used else "verified", [])
