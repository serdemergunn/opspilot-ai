"""Contract and end-to-end checks against a running .NET API.

Skipped unless OPSPILOT_LIVE_API_URL and OPSPILOT_SERVICE_KEY are set, e.g.:
    OPSPILOT_LIVE_API_URL=http://127.0.0.1:8080 OPSPILOT_SERVICE_KEY=... pytest tests/ai
"""

import asyncio
import os
from datetime import date

import httpx
import pytest

import reference_metrics as oracle
from opspilot_ai.agent import Agent
from opspilot_ai.config import Settings
from opspilot_ai.providers.deterministic import DeterministicProvider
from opspilot_ai.schemas import ChatRequest
from opspilot_ai.tools import TOOLS, ToolClient

URL, KEY = os.environ.get("OPSPILOT_LIVE_API_URL"), os.environ.get("OPSPILOT_SERVICE_KEY")
pytestmark = pytest.mark.skipif(not (URL and KEY), reason="needs a running API (OPSPILOT_LIVE_API_URL, OPSPILOT_SERVICE_KEY)")


def test_tool_schemas_match_the_api():
    published = httpx.get(f"{URL}/internal/tools", headers={"X-OpsPilot-Service-Key": KEY}).json()["tools"]
    api = {t["name"]: t["input_schema"] for t in published}
    assert set(api) == set(TOOLS)
    for name, spec in TOOLS.items():
        ours = spec.input_schema()
        assert set(ours["properties"]) == set(api[name]["properties"]), name
        assert ours["required"] == api[name]["required"], name
        assert ours["additionalProperties"] is api[name]["additionalProperties"] is False


def test_acceptance_question_end_to_end(dataset):
    async def run():
        client = ToolClient(URL, KEY, 10.0)
        try:
            agent = Agent(Settings(api_base_url=URL, service_key=KEY), client, lambda m: DeterministicProvider())
            return await agent.run(ChatRequest(messages=[{"role": "user", "content": "Which production line had the most downtime last week?"}]), "demo")
        finally:
            await client.aclose()

    r = asyncio.run(run())
    expected = oracle.downtime_by_line(dataset, date(2026, 11, 4), date(2026, 11, 10))
    assert r.charts[0].data == [{k: i[k] for k in ("line_code", "line_name", "downtime_hours", "downtime_minutes", "share_pct")} for i in expected["items"]]
    assert f"{expected['items'][0]['downtime_minutes']:,}" in r.summary
