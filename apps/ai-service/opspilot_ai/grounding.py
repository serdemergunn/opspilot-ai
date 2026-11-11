"""Number grounding: every number in an answer must come from a tool result.

This is a deterministic check, independent of the model. A number in a finding is accepted when it
equals a value in the referenced tool results at the precision it is written with ("verified"), or the
absolute difference of two such values ("derived", e.g. a change in percentage points). Anything else is
treated as fabricated and the finding is removed.

Identifiers are not quantities and are ignored: dates, line names ("Line 04", "L04"), error codes ("E104").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from itertools import combinations
from typing import Any, Iterable, Literal

_MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
_IDENTIFIERS = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),  # ISO dates
    re.compile(rf"\b{_MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,\s*\d{{4}})?", re.IGNORECASE),  # Nov 4, 2026
    re.compile(rf"\b\d{{1,2}}\s+{_MONTHS}(?:\s+\d{{4}})?", re.IGNORECASE),  # 4 Nov 2026
    re.compile(rf"\b{_MONTHS}\s+\d{{4}}\b", re.IGNORECASE),  # October 2026
    re.compile(r"\b(?:production\s+)?lines?\s+0?\d{1,2}\b", re.IGNORECASE),  # Line 04
    re.compile(r"\bL\d{2}\b"),  # L04
    re.compile(r"\b[A-Z]\d{3}\b"),  # E104
    re.compile(r"\b[A-Z]\d{2}-EQ\d{2}\b"),  # L04-EQ02
    re.compile(r"\b(?:phase|milestone)\s+\d+\b", re.IGNORECASE),  # roadmap references, e.g. "Phase 2"
]
_NUMBER = re.compile(r"(?<![\w.])[-−+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w])")


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


def collect_values(obj: Any) -> set[Decimal]:
    """All numeric leaves of tool results, plus list lengths (e.g. "3 reasons", "6 lines")."""
    values: set[Decimal] = set()

    def walk(o: Any) -> None:
        if isinstance(o, bool) or o is None:
            return
        if isinstance(o, (int, float)):
            values.add(abs(Decimal(str(o))))
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            values.add(Decimal(len(o)))
            for v in o:
                walk(v)

    walk(obj)
    return values


def _round(v: Decimal, decimals: int) -> Decimal:
    return v.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


Verdict = Literal["verified", "derived", "no_numbers", "ungrounded"]


@dataclass
class CheckResult:
    verdict: Verdict
    ungrounded: list[str]


def check_text(text: str, values: Iterable[Decimal], allow_derived: bool = True, max_pair_values: int = 600) -> CheckResult:
    numbers = extract_numbers(text)
    if not numbers:
        return CheckResult("no_numbers", [])
    pool = sorted(set(values))
    derived_used = False
    ungrounded: list[str] = []
    differences: set[Decimal] | None = None
    for n in numbers:
        if any(_round(v, n.decimals) == n.value for v in pool):
            continue
        if allow_derived and len(pool) <= max_pair_values:
            if differences is None:
                differences = {abs(a - b) for a, b in combinations(pool, 2)}
            if any(_round(d, n.decimals) == n.value for d in differences):
                derived_used = True
                continue
        ungrounded.append(n.raw)
    if ungrounded:
        return CheckResult("ungrounded", ungrounded)
    return CheckResult("derived" if derived_used else "verified", [])
