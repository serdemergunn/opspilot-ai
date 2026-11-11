# OpsPilot AI — Architecture Review and Phase 1 Plan

Status: **accepted for Phase 1** · Last updated: 2026-11-11

This document is the working plan for the first phase. It records what we build, what we
deliberately do not build yet, and the contracts between the three applications.
Metric formulas live in [metric-definitions.md](metric-definitions.md) and are the single
source of truth for every implementation (C#, Python oracle, evaluation).

---

## 1. Critical architecture review

The brief is sound in its core idea — *the LLM chooses and explains, deterministic code
measures* — but as written it carries more moving parts than a first version needs.
These are the issues worth deciding up front.

### 1.1 Three runtimes and two databases is the main complexity cost

React + ASP.NET Core + Python, plus SQL Server **and** PostgreSQL, means five things to
build, containerize, health-check and test before the first answer appears.

**Decision:** keep the three applications (each one demonstrates a distinct skill and has a
clear responsibility), but **do not introduce PostgreSQL/pgvector until Phase 3**. Phase 1
runs on SQL Server only.

*Alternative considered:* PostgreSQL for both operational data and vectors (one database,
EF Core works fine with Npgsql). It is simpler, but the brief explicitly targets the
.NET + SQL Server stack, and keeping the vector store separate makes the "structured
analytics vs. RAG" boundary visible. Revisit if the Compose setup becomes painful.

### 1.2 Who owns the tools — the AI service must not touch the database

If the Python service queried SQL Server directly, there would be two data-access
implementations, two places to enforce limits, and a privileged credential inside the
component that processes untrusted text.

**Decision:** the .NET API is the **only** component that reads operational data.
Agent tools in Python are thin, typed clients: Pydantic validates arguments (fast feedback
to the model), then the call goes to an allowlisted .NET tool endpoint, which validates
again and is **authoritative**. The .NET analytics path uses a read-only SQL login.
See [ADR 0001](../decisions/0001-allowlisted-tools-instead-of-text-to-sql.md) and
[ADR 0002](../decisions/0002-dotnet-api-as-gateway-and-tool-authority.md).

### 1.3 Request routing: one public origin

Options: (a) browser → AI service directly for chat, (b) browser → .NET → AI service.

**Decision:** (b). The browser talks only to the .NET API, which proxies `/api/chat` to the
AI service. Authentication (Phase 5) and rate limiting then live in one place, and the AI
service is never exposed publicly. The cost is a call loop (API → AI service → API tool
endpoints), which is acceptable and common for a gateway pattern; tool endpoints are on an
internal route protected by a service key.

### 1.4 "Last week" needs a pinned clock

A synthetic dataset ends on a fixed date; real "now" keeps moving. If relative dates used the
wall clock, the demo would show empty results a week after seeding, and evaluation expected
values would drift.

**Decision:** the dataset covers 90 full UTC days ending at a **pinned reference time**
(`2026-11-11T00:00:00Z`). The API resolves relative ranges against a configurable
`OpsPilot:Clock:ReferenceTimeUtc` (Compose: `OPSPILOT_REFERENCE_TIME_UTC`); unset means wall clock. See
[ADR 0003](../decisions/0003-pinned-demo-clock-and-independent-oracle.md).

Time zones: all persistent timestamps are UTC. Tool arguments are plant-local calendar dates
(`YYYY-MM-DD`) plus an explicit plant time zone from configuration; the API converts to a
half-open UTC interval before querying. The demo plant time zone is `UTC` so that dataset days
and calendar days coincide; the conversion path is still exercised in tests with a non-UTC zone.

### 1.5 Numbers must be checkable without an LLM

"Never fabricate metrics" needs a mechanism, not a prompt instruction. Three layers:

1. **Charts and tables are built from tool outputs by code**, never from LLM text.
2. **Number grounding check** (Phase 1, AI service): every numeric value in a finding of kind
   `measurement` or `calculation` must match a value in a referenced tool result (within the
   documented rounding). Failing findings are dropped or downgraded and a warning is shown.
3. **Independent oracle**: a stdlib-only Python implementation of the metric definitions
   ([`sample-data/reference_metrics.py`](../../sample-data/reference_metrics.py)) produces
   golden values. The C# implementation must match them exactly; the agent evaluation uses
   them to check numeric accuracy.

### 1.6 Demo mode should run the same graph

A separate "fake chat" path would prove nothing. **Decision:** demo mode is an LLM provider
implementation (`DeterministicProvider`) behind the same provider interface: rule-based intent
matching selects tools, the real tools run against the real data, and a template renders the
narrative. Responses are labeled **"Demo mode — deterministic response, not generated by an
LLM"** in both the payload (`mode: "demo"`) and the UI.

### 1.7 Things cut or deferred from Phase 1

| Item | Phase 1 decision | Why |
|---|---|---|
| PostgreSQL / pgvector / RAG | Phase 3 | Not needed for structured analytics |
| OpenTelemetry | Phase 4; structured JSON logs + correlation ID now | Correlation IDs give 80% of the value early |
| Streaming responses | Phase 2 | Request/response is enough to validate the graph |
| Auth | Not in MVP; all ports bound to `127.0.0.1` | Synthetic data only; documented limitation |
| Conversation persistence | Client holds history; AI service is stateless | Avoids a session store |
| Equipment/maintenance/quality **tools** | Tables + seed now, tools in Phase 2 | Data shape is fixed early, tool surface stays small |
| ApexCharts | Recharts only | One chart library |
| Multi-agent | Single LangGraph graph | As the brief recommends |

### 1.8 Schema refinements to the brief

- **`DowntimeReasons` lookup table** (`Code`, `Name`, `Category`, `IsPlanned`). Planned vs.
  unplanned downtime is the first question any operations manager asks.
- **`DowntimeEvents.EquipmentId` (nullable)**. Links failures to equipment and maintenance
  events, which Phase 2 needs for "why" questions.
- **`ProductionRecords.PeriodStartUtc`** instead of `Timestamp`: each record is a one-hour
  bucket, and the name says so.
- **`ProductionLines.Code`** (`L01`…`L06`) as the stable external identifier used by tools;
  surrogate integer IDs never leave the API.

---

## 2. Exact MVP scope (Phase 1)

**In scope**

1. Synthetic dataset: 6 lines, 24 equipment units, 90 days of hourly production, downtime,
   quality incidents and maintenance events, with three seeded scenarios (§3.3).
2. SQL Server schema (EF Core migrations) and a seeder that loads the committed CSVs.
3. ASP.NET Core read-only analytics endpoints for the dashboard and three internal tool endpoints.
4. React dashboard: Overview page (KPIs, daily trend, downtime by line, downtime reasons).
5. FastAPI AI service with one LangGraph graph, three tools, provider abstraction with
   `DeterministicProvider` (demo) and one live provider (Anthropic; OpenAI second).
6. AI Analyst page: chat, chart from tool results, findings by kind, source per metric, a basic
   tool-call list.
7. Docker Compose for SQL Server, API, AI service, web.
8. Deterministic unit tests for every calculation, plus golden-value parity tests.

**Out of scope for Phase 1:** everything in §1.7, the remaining navigation pages (rendered as
"coming in Phase N" placeholders), evaluation runner, CI beyond build + unit tests.

**Phase 1 acceptance (from the brief):** a reviewer runs `docker compose up`, opens the
dashboard, asks *"Which production line had the most downtime last week?"* in demo mode or with
an API key, and gets an answer whose numbers match the golden values exactly, with a bar chart of
downtime by line and the tool call shown as the source.

---

## 3. Data model

### 3.1 Entities

```
ProductionLines 1───* Equipment 1───* MaintenanceEvents
      │  1                 │ 0..1
      ├───* ProductionRecords
      ├───* DowntimeEvents *───1 DowntimeReasons
      │          └───────────────*─0..1 Equipment
      └───* QualityIncidents
```

| Table | Columns | Notes |
|---|---|---|
| `ProductionLines` | `Id` int PK, `Code` varchar(8) unique, `Name`, `Department`, `NominalRatePerHour` int, `IsActive` bit | |
| `Equipment` | `Id` PK, `LineId` FK, `EquipmentCode` unique, `Name`, `EquipmentType` | |
| `DowntimeReasons` | `Code` varchar(32) PK, `Name`, `Category`, `IsPlanned` bit | lookup |
| `ProductionRecords` | `Id` bigint PK, `LineId` FK, `PeriodStartUtc` datetime2, `PlannedQuantity`, `ProducedQuantity`, `DefectiveQuantity` | unique (`LineId`,`PeriodStartUtc`); CHECK `0 ≤ Defective ≤ Produced` |
| `DowntimeEvents` | `Id` PK, `LineId` FK, `EquipmentId` FK null, `StartTimeUtc`, `EndTimeUtc`, `DurationMinutes`, `ReasonCode` FK, `Description` | CHECK `End > Start`; index (`LineId`,`StartTimeUtc`) incl. `EndTimeUtc` |
| `QualityIncidents` | `Id` PK, `LineId` FK, `OccurredAtUtc`, `Category`, `Severity`, `Description`, `Status` | Severity ∈ Low/Medium/High/Critical; Status ∈ Open/Investigating/Resolved |
| `MaintenanceEvents` | `Id` PK, `EquipmentId` FK, `DowntimeEventId` FK null, `OccurredAtUtc`, `ErrorCode` null, `Description`, `Resolution`, `DurationMinutes` | `ErrorCode` null for preventive work |

`MaintenanceEvents.DowntimeEventId` links a corrective repair to the stoppage it caused, so
"what caused Line 04's downtime" can be answered from data instead of inferred.

EF Core migrations own the DDL (Milestone 2). The CSV headers in `sample-data/csv/` are the
interchange contract between the generator and the seeder.

### 3.2 Database access

- `opspilot_migrator` — DDL + seed, used only by the seeder at startup.
- `opspilot_reader` — `db_datareader` only, used by every analytics query.

### 3.3 Seeded scenarios (so the demo has something to find)

| Scenario | Where | Expected discovery |
|---|---|---|
| Spindle overtemperature (E104) on `L04-EQ02` recurring in the last 21 days | Line 04 | Line 04 has the most downtime last week; mechanical failure is its top reason |
| 6-hour electrical outage on 2026-11-10 06:00–12:00 UTC | Line 02 | "Why did efficiency drop yesterday?" |
| Elevated seal-integrity incidents and defect rate in the last 30 days | Line 03 | "Which quality issues first?" (Phase 2 tool) |

---

## 4. API contracts

All JSON uses `camelCase` on the public .NET API and `snake_case` in tool schemas and the AI
service (Python convention; tool names and arguments are what the model sees). The .NET API
serializes tool endpoints in `snake_case` to keep one schema.

### 4.1 React ↔ .NET API (public, `/api`)

| Method & path | Purpose |
|---|---|
| `GET /api/health` | Liveness + DB connectivity |
| `GET /api/meta` | Reference time, plant time zone, dataset range, mode (`demo`/`live`) |
| `GET /api/lines` | Lines with codes and departments |
| `GET /api/analytics/production-summary?startDate&endDate&lineCodes` | KPI cards |
| `GET /api/analytics/downtime-by-line?startDate&endDate&lineCodes&topN` | Bar chart |
| `GET /api/analytics/downtime-reasons?startDate&endDate&lineCodes&topN` | Reason distribution |
| `GET /api/analytics/daily-trend?startDate&endDate&lineCodes` | Trend chart (dashboard only in Phase 1) |
| `POST /api/chat` | Proxied to the AI service |

Errors use RFC 7807 `application/problem+json` with a `traceId`.

### 4.2 .NET API → AI service (internal)

`POST /v1/chat`

```json
{
  "messages": [{ "role": "user", "content": "Which production line had the most downtime last week?" }],
  "context": { "reference_time_utc": "2026-11-11T00:00:00Z", "timezone": "UTC" },
  "mode": "demo"
}
```

Response (`ChatResponse`):

```json
{
  "answer_id": "ans_01J…",
  "mode": "demo",
  "provider": "deterministic",
  "summary": "Line 04 had the most downtime in the last 7 days.",
  "findings": [
    {
      "id": "f1",
      "kind": "calculation",
      "text": "Line 04 recorded 1,234 minutes of downtime, 41.2% of the total.",
      "evidence": [{ "tool_call_id": "tc1", "fields": ["items[0].downtime_minutes", "items[0].share_pct"] }]
    },
    { "id": "f2", "kind": "hypothesis", "text": "Recurring mechanical faults may be contributing.", "evidence": [] }
  ],
  "charts": [
    {
      "id": "c1", "type": "bar", "title": "Downtime by line, 2026-11-04 to 2026-11-10",
      "x_key": "line_code", "series": [{ "key": "downtime_minutes", "label": "Downtime (min)" }],
      "data": [{ "line_code": "L04", "downtime_minutes": 1234 }],
      "source_tool_call_id": "tc1"
    }
  ],
  "tool_calls": [
    {
      "id": "tc1", "tool": "get_downtime_by_line", "status": "succeeded",
      "arguments": { "start_date": "2026-11-04", "end_date": "2026-11-10" },
      "duration_ms": 42, "result_summary": "6 lines, 2,996 total downtime minutes"
    }
  ],
  "warnings": [],
  "usage": { "tool_calls": 1, "max_tool_calls": 6, "input_tokens": 0, "output_tokens": 0 }
}
```

(Numbers above are illustrative placeholders, not dataset values.)

`finding.kind` ∈ `measurement | calculation | pattern | hypothesis | recommendation`.
`tool_call.status` ∈ `succeeded | failed | rejected | timeout`.

### 4.3 AI service → .NET API (internal tool endpoints)

`POST /internal/tools/{tool_name}` with header `X-OpsPilot-Service-Key`; body is the tool
arguments object. Unknown tool names return 404 — the allowlist lives in the API's tool
registry. Response envelope:

```json
{
  "tool": "get_downtime_by_line",
  "status": "ok",
  "data": { "...": "tool-specific, see §5" },
  "meta": {
    "window_start_utc": "2026-11-04T00:00:00Z",
    "window_end_utc": "2026-11-11T00:00:00Z",
    "row_count": 6, "truncated": false, "query_ms": 12,
    "source": "sqlserver:opspilot.DowntimeEvents",
    "metric_definitions_version": "1"
  }
}
```

Validation failures: HTTP 422 with `status: "invalid_arguments"` and per-field errors, which the
agent may use for **one** corrective retry.

---

## 5. The first three tools

Shared argument rules (enforced in Pydantic **and** in .NET):

- `start_date`, `end_date`: plant-local calendar dates, inclusive; `end_date ≥ start_date`;
  range ≤ 92 days; both within the dataset range relative to the reference clock.
- `line_codes`: optional; 1–10 items matching `^L\d{2}$`; unknown codes → 422.
- `top_n`: 1–20, default 10.
- `additionalProperties: false` everywhere.

```json
{
  "name": "get_production_summary",
  "description": "Totals of planned, produced and defective units, attainment, defect rate and downtime for a date range, overall and per line. Read-only.",
  "input_schema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["start_date", "end_date"],
    "properties": {
      "start_date": { "type": "string", "format": "date", "description": "Inclusive, plant-local (YYYY-MM-DD)." },
      "end_date":   { "type": "string", "format": "date", "description": "Inclusive, plant-local (YYYY-MM-DD)." },
      "line_codes": { "type": "array", "items": { "type": "string", "pattern": "^L\\d{2}$" }, "minItems": 1, "maxItems": 10, "uniqueItems": true }
    }
  }
}
```

Output `data`:
`{ totals: { planned_quantity, produced_quantity, defective_quantity, good_quantity, attainment_pct, defect_rate_pct, downtime_minutes, downtime_hours, record_count }, by_line: [ { line_code, line_name, ...same fields } ] }`

```json
{
  "name": "get_downtime_by_line",
  "description": "Downtime minutes, event count and share of total per production line for a date range, sorted by downtime descending. Read-only.",
  "input_schema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["start_date", "end_date"],
    "properties": {
      "start_date": { "type": "string", "format": "date" },
      "end_date":   { "type": "string", "format": "date" },
      "line_codes": { "type": "array", "items": { "type": "string", "pattern": "^L\\d{2}$" }, "minItems": 1, "maxItems": 10, "uniqueItems": true },
      "include_planned": { "type": "boolean", "default": true, "description": "Include planned downtime (changeovers, planned maintenance)." },
      "top_n": { "type": "integer", "minimum": 1, "maximum": 20, "default": 10 }
    }
  }
}
```

Output `data`:
`{ total_downtime_minutes, items: [ { line_code, line_name, downtime_minutes, downtime_hours, event_count, share_pct } ], omitted_count }`

```json
{
  "name": "get_downtime_reasons",
  "description": "Downtime grouped by reason code with minutes, event count and share of total for a date range, optionally filtered by line. Read-only.",
  "input_schema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["start_date", "end_date"],
    "properties": {
      "start_date": { "type": "string", "format": "date" },
      "end_date":   { "type": "string", "format": "date" },
      "line_codes": { "type": "array", "items": { "type": "string", "pattern": "^L\\d{2}$" }, "minItems": 1, "maxItems": 10, "uniqueItems": true },
      "include_planned": { "type": "boolean", "default": true },
      "top_n": { "type": "integer", "minimum": 1, "maximum": 20, "default": 10 }
    }
  }
}
```

Output `data`:
`{ total_downtime_minutes, items: [ { reason_code, reason_name, category, is_planned, downtime_minutes, downtime_hours, event_count, share_pct } ], omitted_count }`

### 5.1 Agent graph (Phase 1)

```
understand ─▶ plan ─▶ execute_tools ─▶ validate_evidence ─┬─▶ respond ─▶ ground_check ─▶ END
                ▲                                          │
                └──────── need_more_evidence (≤ 2 loops) ──┘
   unsupported / out-of-scope ─────────────────────────────▶ respond (refusal template)
```

Hard limits (config, enforced in code — not by the model): max 6 tool calls per request,
max 2 planning iterations, 10 s per tool call, 45 s per request, 1 retry on 422, token budget
per request. The model's output never authorizes anything: the tool registry decides what
exists, the API decides what is allowed.

---

## 6. Milestones

| # | Milestone | Runnable result | Needs |
|---|---|---|---|
| **M0** ✓ | Plan + repository skeleton | This document, ADRs, layout | — |
| **M1** ✓ | Data foundation | Deterministic generator, committed CSVs, independent metric oracle, golden values, tests, CI | Python 3.12+ (stdlib only) |
| **M2** ✓ | Analytics API | EF Core schema + migrations, CSV seeder, 4 dashboard endpoints, 3 tool endpoints, xUnit unit tests + golden parity (Testcontainers), Compose with SQL Server + API | .NET 8 SDK, Docker |
| **M3** ✓ | Dashboard | React Overview page against M2, loading/empty/error states | Node 20+ |
| **M4** ✓ | AI service | FastAPI, Pydantic tool clients, LangGraph graph, `DeterministicProvider`, Anthropic provider, grounding check, pytest with fake provider and stubbed API | Python 3.12 |
| M5 | AI Analyst + E2E | Chat page, chart from tool results, tool list, `/api/chat` proxy, full Compose, **Phase 1 acceptance** | all |

Phases 2–5 follow the brief; each will get its own plan section when Phase 1 is accepted.

---

## 7. Milestone 1 acceptance criteria

1. `python sample-data/generate.py` regenerates the committed CSVs **byte-for-byte**
   (no third-party packages, independent of OS line endings).
2. The dataset contains 6 lines, 24 equipment units, and exactly 6 × 90 × 24 = 12,960 hourly
   production records covering `2026-08-13T00:00:00Z` – `2026-11-11T00:00:00Z`.
3. Integrity: every foreign key resolves; no two downtime events on the same line overlap;
   `EndTimeUtc − StartTimeUtc = DurationMinutes`; `0 ≤ Defective ≤ Produced`; all timestamps
   are minute-aligned UTC.
4. The reference metric implementation passes hand-computed fixture tests covering window
   clipping, empty windows, line filtering, `top_n` truncation, planned/unplanned filtering and
   rounding at `.x5` midpoints.
5. `python sample-data/reference_metrics.py --check` confirms the committed golden file matches
   the current data and code.
6. The seeded scenarios are detectable in the golden values (Line 04 leads downtime in the last
   7 days; Line 02 has an outage on 2026-11-10).
7. `python -m unittest discover -s tests/data -t .` passes locally and in GitHub Actions.
