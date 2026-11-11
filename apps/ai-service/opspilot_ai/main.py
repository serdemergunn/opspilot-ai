"""FastAPI entry point. Internal service: called only by the .NET API (ADR 0002), protected by a service key."""

from __future__ import annotations

import asyncio
import hmac
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Request

from .agent import Agent
from .config import Mode, Settings
from .providers.anthropic_provider import create_anthropic_provider
from .providers.base import Provider
from .providers.deterministic import DeterministicProvider
from .schemas import ChatRequest, ChatResponse
from .tools import ToolClient

logging.basicConfig(level=logging.INFO, format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":%(message)r}')


def make_provider_factory(settings: Settings):
    def factory(mode: Mode) -> Provider:
        if mode == "live":
            return create_anthropic_provider(settings.anthropic_model, settings.anthropic_effort, settings.max_output_tokens,
                                             timeout_s=settings.request_timeout_s - 5)
        return DeterministicProvider()

    return factory


def create_app(settings: Settings | None = None, tools: ToolClient | None = None, provider_factory=None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = tools or ToolClient(settings.api_base_url, settings.service_key, settings.tool_timeout_s)
        app.state.agent = Agent(settings, client, provider_factory or make_provider_factory(settings))
        yield
        await client.aclose()

    app = FastAPI(title="OpsPilot AI service", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "default_mode": settings.mode}

    @app.post("/v1/chat", response_model=ChatResponse)
    async def chat(body: ChatRequest, request: Request, x_opspilot_service_key: str = Header(default="")) -> ChatResponse:
        # Fail closed when no key is configured; compare in constant time.
        if not settings.service_key or not hmac.compare_digest(x_opspilot_service_key.encode(), settings.service_key.encode()):
            raise HTTPException(status_code=401, detail="unauthorized")
        mode: Mode = body.mode or settings.mode
        notes: list[str] = []
        if mode == "live" and not settings.allow_live:
            mode = "demo"
            notes.append("Live mode is disabled on this server (set OPSPILOT_ALLOW_LIVE=true and ANTHROPIC_API_KEY to enable it); "
                         "this answer comes from the deterministic demo pipeline.")
        try:
            return await request.app.state.agent.run(body, mode, notes)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="The request exceeded the time limit.") from None

    return app


app = create_app()
