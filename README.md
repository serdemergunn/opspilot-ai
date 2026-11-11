# OpsPilot AI

[![CI](https://github.com/serdemergunn/opspilot-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/serdemergunn/opspilot-ai/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**An AI analyst for manufacturing operations that answers questions from database records and refuses to
show a number it cannot trace to a tool result.**

## In 60 seconds

- **What it does:** you ask *"Which production line had the most downtime last week?"*; an agent picks
  read-only analytics tools, the .NET API runs fixed, parameterized queries, and the answer comes back with a
  chart, the tool calls behind it and every statement labeled as *measurement, calculation, pattern,
  hypothesis* or *suggested action*.
- **What makes it more than an LLM wrapper:**
  - **No text-to-SQL.** The model can only propose calls to 4 allowlisted, schema-validated, read-only tools.
  - **Code, not the model, enforces the rules:** tool and round limits, timeouts, the token budget, data-coverage checks.
  - **A grounding check runs after every answer.** Statements whose numbers don't appear in the cited tool
    results are removed.
  - **Metrics are implemented twice,** in C# and in an independent Python oracle. CI requires both to agree
    on 29 golden cases.
- **Stack:** React + TypeScript · ASP.NET Core 8 + EF Core + SQL Server · Python FastAPI + LangGraph ·
  Claude (Anthropic) · Docker Compose · GitHub Actions.
- **Status:** Phase 1 (working MVP) is complete and audited ([technical audit](docs/technical-audit.md)).
  Runs without an API key in a clearly labeled demo mode.
  Live Claude answers are implemented but **not yet verified against the real API** (see the audit).

![AI Analyst answering "Which production line had the most downtime last week?" with labeled findings, a chart and the tool-call timeline](docs/screenshots/ai-analyst.png)

<details>
<summary><b>More screenshots</b>: a multi-tool answer and the operations dashboard</summary>

**"Why did production efficiency decrease yesterday?"** The answer uses four tool calls, a derived
calculation (83.1% → 79.8%, a 3.3-point change computed from two tool results) and a hypothesis that is
explicitly marked as unverified.

![Multi-tool answer with verified measurements, a derived calculation, patterns, a hypothesis and a suggested action](docs/screenshots/ai-analyst-multi-tool.png)

**Overview dashboard.** Every chart has a table view and names the endpoint, tables and row count behind it.

![Operations dashboard with KPI tiles, daily attainment, downtime by line and downtime reasons](docs/screenshots/overview.png)

</details>

Screenshots show demo mode on the synthetic dataset; `scripts/screenshots` regenerates them from a running stack.

## Implemented vs planned

| Area | Implemented and tested | Planned |
|---|---|---|
| Data | Deterministic synthetic plant (6 lines, 90 days), SQL Server schema, seeding, read-only login | — |
| Analytics API | 4 dashboard endpoints, 4 allowlisted agent tools, validation, problem details | Quality, equipment and comparison tools (Phase 2) |
| Agent | LangGraph plan → execute → validate → answer → ground loop, limits, failure handling, data-coverage warnings | Streaming, more tools, evaluation runner (Phases 2 and 4) |
| LLM | Anthropic provider (`claude-opus-5-5`); deterministic demo provider; graceful fallback | Live answers verified against the real API; other providers |
| UI | Overview dashboard, AI Analyst with findings, charts, tool calls and timeline | Production, Downtime, Quality, Knowledge Base, Agent Activity and Evaluations pages (shown as placeholders) |
| RAG | — | pgvector knowledge base with citations (Phase 3) |
| Ops | Docker Compose, CI (4 jobs), JSON logs, rate limiting | OpenTelemetry, authentication (required before any public deployment) |

## 2-minute demo

Requires Docker. No API key is needed.

```bash
git clone https://github.com/serdemergunn/opspilot-ai.git && cd opspilot-ai
cp .env.example .env   # set MSSQL_SA_PASSWORD, OPSPILOT_DB_READER_PASSWORD, OPSPILOT_SERVICE_KEY
docker compose up --build -d
```

Open **http://127.0.0.1:3000/analyst** and ask:

1. *Which production line had the most downtime last week?* You'll see Line 04 with 2,903 minutes (40.3%),
   a chart built from the `get_downtime_by_line` result, and the tool call in the timeline.
2. *Why did production efficiency decrease yesterday?* Four tool calls run. Attainment fell from 83.1% to
   79.8%, and the hypothesis is labeled as not verified.
3. *Which line had the most downtime in March 2026?* The answer is "No data is available", and a warning
   names the range the dataset actually covers. A period with no records is not reported as zero downtime.
4. *Which line will have the most downtime next week?* The agent declines, because it doesn't forecast.

To see the grounding check remove a fabricated number, run the agent tests (they don't need Docker):

```bash
python -m pytest tests/ai -q -k "fabricated or unverifiable or ordinary_words"   # in the apps/ai-service venv
```

## Core ideas

- **Allowlisted tools, never text-to-SQL.** The model chooses among typed operations with bounded parameters;
  the .NET API validates and executes them read-only. ([ADR 0001](docs/decisions/0001-allowlisted-tools-instead-of-text-to-sql.md))
- **One authority for data access.** The AI service holds no database credentials.
  ([ADR 0002](docs/decisions/0002-dotnet-api-as-gateway-and-tool-authority.md))
- **Numbers are verifiable without an LLM.** An independent implementation of the metric definitions produces
  golden values that the API and the agent are tested against. ([ADR 0003](docs/decisions/0003-pinned-demo-clock-and-independent-oracle.md))
- **Code-enforced grounding and an honest demo mode.** The demo mode runs the same graph and tools, and its
  answers are labeled as deterministic. ([ADR 0004](docs/decisions/0004-grounding-check-and-deterministic-demo-provider.md))

## Architecture

```
React (Vite, TanStack Query, Recharts)          nginx: serves the app, proxies /api, blocks /internal
        │  /api/*
        ▼
ASP.NET Core 8 API ──── read-only login ────▶ SQL Server
   │  /api/chat (validated, rate limited)     ▲
   ▼                                          │ POST /internal/tools/{name}  (allowlist, service key)
FastAPI + LangGraph agent ────────────────────┘
   └─ provider: Anthropic (live, opt-in) | Deterministic (demo)
```

## Running and testing

| Service | Address (localhost only) |
|---|---|
| Web (dashboard + AI Analyst) | http://127.0.0.1:3000 |
| .NET API | http://127.0.0.1:8080 |
| AI service (debugging) | http://127.0.0.1:8090 |
| SQL Server | 127.0.0.1:14333 |

**Live mode (Claude).** Set `ANTHROPIC_API_KEY` and `OPSPILOT_ALLOW_LIVE=true` in `.env`, restart, and pick
**Live (Claude)** on the AI Analyst page. Live mode is off unless the server enables it, because every request
is billed. Without a key, live requests fall back to demo mode and say so in their warnings.

| Endpoint | Purpose |
|---|---|
| `GET /api/health`, `/api/meta`, `/api/lines` | Status, pinned clock, dataset range, lines |
| `GET /api/analytics/{production-summary, downtime-by-line, downtime-reasons, daily-trend}` | Dashboard data |
| `POST /api/chat` | Ask the agent: validated (64 KB, 20 messages, 16,000 characters), rate limited per client (20 per minute) |
| `POST /internal/tools/{name}` | Allowlisted read-only agent tools (service key required; not reachable through the web origin) |

```bash
python -m unittest discover -s tests/data -t .   # 23 tests: dataset integrity and the metric oracle (stdlib only)
dotnet test OpsPilot.sln                          # 93 tests: unit tests plus SQL Server integration via Testcontainers
(cd apps/web && npm test)                         # 13 tests
python -m pytest tests/ai -q                      # 98 tests: agent graph, tools, grounding, limits, injection (apps/ai-service venv)
```

Optional suites, skipped by default:

- `tests/ai/test_live_api_contract.py` runs against a running API. Set `OPSPILOT_LIVE_API_URL` and `OPSPILOT_SERVICE_KEY`.
- `tests/ai/test_live_llm.py` makes real Claude calls. Set `ANTHROPIC_API_KEY`; the calls are billed.

The .NET integration suite replays all 29 golden cases through the real HTTP pipeline and SQL Server.
For the dashboard with hot reload, run `cd apps/web && npm ci && npm run dev` (http://127.0.0.1:5173).

## Repository layout

```
apps/web          React dashboard and AI Analyst
apps/api          ASP.NET Core analytics API, tool endpoints, chat proxy
apps/ai-service   FastAPI + LangGraph agent, providers, grounding check
sample-data       generator, CSVs, metric oracle, golden values
tests/            data, backend (.NET), ai (Python)
docs/             architecture plan, metric definitions, ADRs, technical audit, screenshots
scripts/          screenshot capture
```

## Security notes

This is built for local use with synthetic data:

- Every port binds to `127.0.0.1`, and access is anonymous.
- **Authentication and authorization are required before any public deployment.** They are not implemented yet.
- Secrets live in `.env`, which is git-ignored.

Known risks and their mitigations are listed in the [technical audit](docs/technical-audit.md).

## License

MIT — see [LICENSE](LICENSE). All data is synthetic and all names are fictional.
