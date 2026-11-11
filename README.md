# OpsPilot AI

**Agentic operations intelligence for manufacturing — evidence-based answers from deterministic tools, not invented numbers.**

> **Status: early development.** Milestones 1 (data foundation) and 2 (analytics API) are complete.
> The dashboard and the agent are under construction — see the [Phase 1 plan](docs/architecture/phase-1-plan.md).
> Only what is listed under "What works today" is implemented.

OpsPilot AI lets an operations team ask questions such as *"Which production line had the most
downtime last week?"* and get an answer where every number comes from a typed, read-only,
tested backend tool, every chart is built from tool output by code, and every statement is
labeled as a measurement, a calculation, a pattern, a hypothesis or a recommendation.

## Core ideas

- **Allowlisted tools, never text-to-SQL.** The model chooses among typed operations with bounded
  parameters; the .NET API validates and executes them read-only.
  ([ADR 0001](docs/decisions/0001-allowlisted-tools-instead-of-text-to-sql.md))
- **One authority for data access.** The AI service holds no database credentials.
  ([ADR 0002](docs/decisions/0002-dotnet-api-as-gateway-and-tool-authority.md))
- **Numbers are verifiable without an LLM.** A second, independent implementation of the metric
  definitions produces golden values that the API and the agent are tested against.
  ([ADR 0003](docs/decisions/0003-pinned-demo-clock-and-independent-oracle.md))
- **Demo mode without API keys**, using the same graph and real tools, clearly labeled as
  deterministic output.

## Architecture (Phase 1 target)

```
React (Vite, TanStack Query, Recharts)
        │  /api/*
        ▼
ASP.NET Core 8 API ──── read-only login ────▶ SQL Server
   │  /api/chat (proxy)        ▲
   ▼                           │ POST /internal/tools/{name}  (allowlist, service key)
FastAPI + LangGraph agent ─────┘
   └─ provider: Anthropic | OpenAI | Deterministic (demo)
```

PostgreSQL + pgvector for the knowledge base arrives in Phase 3.

## What works today

### Run the API (Docker)

```bash
cp .env.example .env        # then set MSSQL_SA_PASSWORD, OPSPILOT_DB_READER_PASSWORD, OPSPILOT_SERVICE_KEY
docker compose up --build -d
curl http://127.0.0.1:8080/api/meta
curl "http://127.0.0.1:8080/api/analytics/downtime-by-line?startDate=2026-11-04&endDate=2026-11-10"
```

On first start the API applies EF Core migrations, seeds the synthetic dataset and creates a
`db_datareader`-only login that serves every request. The clock is pinned to
`2026-11-11T00:00:00Z` so "last week" matches the dataset.

| Endpoint | Purpose |
|---|---|
| `GET /api/health`, `/api/meta`, `/api/lines` | Status, pinned clock, dataset range, lines |
| `GET /api/analytics/{production-summary, downtime-by-line, downtime-reasons, daily-trend}` | Dashboard data (camelCase) |
| `GET /internal/tools` | Tool list with strict JSON schemas (service key required) |
| `POST /internal/tools/{name}` | Allowlisted, read-only agent tools (snake_case, service key required) |

### Tests

```bash
python -m unittest discover -s tests/data -t .   # dataset integrity + metric oracle (stdlib only)
dotnet test OpsPilot.sln                          # 78 tests; integration tests start SQL Server via Testcontainers
```

The integration suite replays all 29 golden cases from the independent Python oracle through the
real HTTP pipeline and SQL Server and requires identical results. It also checks that the request
login cannot write, that unknown tools and extra arguments are rejected, and that a missing service
key returns 401.

See [sample-data/README.md](sample-data/README.md) for the dataset and seeded scenarios, and
[metric-definitions.md](docs/architecture/metric-definitions.md) for exact formulas and rounding.

## Repository layout

```
apps/web          React dashboard and AI Analyst (M3, M5)
apps/api          ASP.NET Core analytics API and tool endpoints (M2 ✓)
apps/ai-service   FastAPI + LangGraph agent (M4)
sample-data       generator, CSVs, metric oracle, golden values (M1 ✓)
tests/            data (M1 ✓), backend (M2 ✓), ai, evaluation
docs/             architecture, ADRs, screenshots
```

## Security notes

Local development only: services will bind to `127.0.0.1` and use anonymous access with synthetic
data. Authentication and authorization are required before any public deployment and are planned
for a later phase. Secrets live in `.env` (see `.env.example`), which is git-ignored.

## License

MIT — see [LICENSE](LICENSE). All data is synthetic and all names are fictional.
