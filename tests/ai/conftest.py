"""Shared fixtures. The fake analytics API is backed by the independent metric oracle
(sample-data/reference_metrics.py), so agent answers are checked against numbers the AI service did not compute."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps" / "ai-service"))
sys.path.insert(0, str(REPO / "sample-data"))

import reference_metrics as oracle  # noqa: E402

from opspilot_ai.config import Settings  # noqa: E402
from opspilot_ai.tools import ToolClient  # noqa: E402

TODAY = "2026-11-11"
SERVICE_KEY = "test-key"


@pytest.fixture(scope="session")
def dataset() -> oracle.Dataset:
    return oracle.load_dataset()


class FakeApi:
    """Mimics the .NET API contract: /api/meta and POST /internal/tools/{name}."""

    def __init__(self, ds: oracle.Dataset):
        self.ds = ds
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.override: Callable[[str, dict[str, Any]], httpx.Response | None] | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("X-OpsPilot-Service-Key") != SERVICE_KEY:
            return httpx.Response(401, json={"status": "unauthorized"})
        if request.url.path == "/api/meta":
            return httpx.Response(200, json={"today": TODAY, "dataset": {"firstDate": "2026-08-13", "lastDate": "2026-11-10"}})
        tool = request.url.path.rsplit("/", 1)[-1]
        args = json.loads(request.content or b"{}")
        self.calls.append((tool, args))
        if self.override and (response := self.override(tool, args)) is not None:
            return response
        if tool not in oracle.TOOLS:
            return httpx.Response(404, json={"tool": tool, "status": "unknown_tool"})
        try:
            data = oracle.run_tool(self.ds, tool, args)
        except ValueError as e:
            return httpx.Response(422, json={"tool": tool, "status": "invalid_arguments", "errors": {"line_codes": [str(e)]}})
        return httpx.Response(200, json={"tool": tool, "status": "ok", "data": data, "meta": {"row_count": 1, "source": "oracle"}})


@pytest.fixture
def fake_api(dataset) -> FakeApi:
    return FakeApi(dataset)


@pytest.fixture
def settings() -> Settings:
    return Settings(api_base_url="http://api.test", service_key=SERVICE_KEY, mode="demo")


@pytest.fixture
def tool_client(fake_api, settings) -> ToolClient:
    return ToolClient(settings.api_base_url, SERVICE_KEY, settings.tool_timeout_s, transport=httpx.MockTransport(fake_api.handler))
