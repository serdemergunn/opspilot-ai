# apps/ai-service — FastAPI + LangGraph agent

Answers operational questions by calling allowlisted, read-only analytics tools on the .NET API and
explaining the results. It holds no database credentials (ADR 0002).

## How a request flows

```
understand → plan → execute_tools → validate_evidence ─┬→ respond → ground_check → response
               ↑                                       │
               └──────── more evidence needed ─────────┘
```

| Stage | What happens | Who decides |
|---|---|---|
| understand | Reject malformed or oversized input; get plant-local "today" from `/api/meta` | code |
| plan | Propose tool calls | provider (Claude, or rules in demo mode) |
| execute_tools | Refuse unknown tools and duplicates, validate arguments (Pydantic), enforce the call budget, call `POST /internal/tools/{name}` concurrently | code + .NET API |
| validate_evidence | Mark each result's data coverage against the dataset range (a window with no records is "no data", never zero), flag contradictory data; loop back while rounds, calls and time remain | code |
| respond | Write a summary and findings labeled measurement / calculation / pattern / hypothesis / recommendation | provider |
| ground_check | Every number in every finding must appear in the tool results the finding cites (or, except for measurements, be the difference of two values of the same small field there); otherwise the finding is removed and a warning says so. Findings with numbers that cite nothing are removed. Charts are built from tool results by code. | code |

Limits (all enforced in code, configurable by environment): 6 tool calls, 3 planning rounds, 10 s per tool
call, 45 s per request, 60,000 tokens per request.

## Providers

- **`demo`** (default): `DeterministicProvider`. Rule-based intent matching and templates; the same graph,
  tools, data and grounding check. Responses say `"mode": "demo"`. No API key needed.
- **`live`**: `AnthropicProvider` (`claude-opus-5-5`, effort `medium`, server-side refusal fallback).
  Claude proposes tool calls and writes the answer as structured JSON. Every model call is bounded by the
  request deadline. Conversation history from the browser is passed as quoted, untrusted context, never as
  assistant turns. If credentials are missing, the budget or time runs out, or the model fails, the request
  degrades to the deterministic pipeline and says so in `warnings`. Live mode is only available when the server
  sets `OPSPILOT_ALLOW_LIVE=true`.

## Run

```bash
python -m venv .venv && .venv/Scripts/pip install --no-deps -r requirements.lock   # Windows
OPSPILOT_SERVICE_KEY=... OPSPILOT_API_URL=http://127.0.0.1:8080 .venv/Scripts/uvicorn opspilot_ai.main:app --port 8090
```

Or with Docker Compose from the repository root (`docker compose up --build`); the service listens on
`127.0.0.1:8090` for local debugging. `POST /v1/chat` requires the `X-OpsPilot-Service-Key` header.

## Test

```bash
python -m pytest ../../tests/ai -q
```

Tests run the real graph and tool client against a fake API backed by the independent metric oracle
(`sample-data/reference_metrics.py`). `tests/ai/test_live_api_contract.py` also checks the tool schemas
against the running .NET API when `OPSPILOT_LIVE_API_URL` and `OPSPILOT_SERVICE_KEY` are set.
The live Anthropic path is covered with a fake SDK client; it has not been exercised against the real API
in this repository's test suite.

## Known limitations

- The grounding check is lexical. It proves a number came from the cited evidence, not that the sentence
  interprets it correctly. A fabricated number that happens to equal a cited value still passes. Measured on a
  typical 3-result answer, about 9% of random integers between 1 and 1000 pass, against 66% before the audit fix.
  See `docs/technical-audit.md`.
- Demo mode understands a fixed set of question shapes; anything else is answered as unsupported.
- `langsmith` is installed as a LangGraph dependency; tracing stays off unless `LANGSMITH_TRACING` is set.
