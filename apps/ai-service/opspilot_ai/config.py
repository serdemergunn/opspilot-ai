"""Environment-based configuration. Secrets come from the environment only and are never logged."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Mode = Literal["demo", "live"]


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    api_base_url: str = "http://127.0.0.1:8080"
    service_key: str = ""
    mode: Mode = "demo"
    # Live mode spends money on every request, so the server decides whether clients may ask for it.
    allow_live: bool = False
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: str = "medium"

    # Hard limits, enforced in code (never delegated to the model).
    max_tool_calls: int = 6
    max_planning_rounds: int = 3
    tool_timeout_s: float = 10.0
    request_timeout_s: float = 45.0
    max_output_tokens: int = 16_000
    token_budget: int = 60_000
    max_question_chars: int = 2_000

    @classmethod
    def from_env(cls) -> "Settings":
        mode = os.environ.get("OPSPILOT_MODE", "demo").strip().lower()
        return cls(
            api_base_url=os.environ.get("OPSPILOT_API_URL", cls.api_base_url).rstrip("/"),
            service_key=os.environ.get("OPSPILOT_SERVICE_KEY", ""),
            mode="live" if mode == "live" else "demo",
            allow_live=mode == "live" or os.environ.get("OPSPILOT_ALLOW_LIVE", "").strip().lower() in ("1", "true", "yes"),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", cls.anthropic_model),
            anthropic_effort=os.environ.get("ANTHROPIC_EFFORT", cls.anthropic_effort),
            max_tool_calls=_int("OPSPILOT_MAX_TOOL_CALLS", cls.max_tool_calls),
            max_planning_rounds=_int("OPSPILOT_MAX_PLANNING_ROUNDS", cls.max_planning_rounds),
            token_budget=_int("OPSPILOT_TOKEN_BUDGET", cls.token_budget),
        )
