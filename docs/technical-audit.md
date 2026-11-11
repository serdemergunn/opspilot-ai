# Technical audit — Phase 1

**Date:** 2026-11-11 · **Baseline:** `8e689fd` (Phase 1 as published) · **Result:** fixes merged in this audit's commit.

**Environment:**
- Windows 11, Docker 29.9.3, .NET SDK 8.0.428, Node 26, Python 3.15 locally.
- CI uses Ubuntu, Python 3.12 and Node 20.

**Method:**
1. Clean clone from GitHub, no-cache image build, and a fresh database volume.
2. Runtime probes against the running stack, including deliberate outages.
3. All test suites.
4. Dependency vulnerability scans.
5. An **independent security review** by a second reviewer that did not see this author's findings.
6. Every finding reproduced before being fixed.

Nothing in this report is claimed without having been executed. Anything not executed is listed as unverified.

---

## 1. Verified working

| Feature | How it was verified |
|---|---|
| Clean build from the public repository | `git clone` + `docker compose build --no-cache`: 3 images in 95 s, no errors |
| Cold start with an empty database | Migrations, CSV seeding and read-only login provisioning; API healthy 11 s after `up` |
| Connectivity web → API → AI service → API tools → SQL Server | `POST /api/chat` through nginx returned Line 04, 2,903 min, 40.3%, identical to the golden values |
| Read-only data access | Integration test: the request login can `SELECT` but `DELETE` fails with a permission error |
| Allowlisted tools only | Unknown tool → 404 without a query; extra arguments → 422; `/internal/*` → 404 from the web origin |
| Numbers in answers come from tool results | The chart data in an agent answer equals the oracle's output for the same window (`test_most_downtime_last_week_matches_the_oracle`, `test_acceptance_question_end_to_end` against the live API) |
| Python ↔ .NET tool schema contract | `test_tool_schemas_match_the_api` against the running API |
| Explicit periods, missing data, forecasts | See section 2.2: probed on the running stack |
| Failure handling | See section 1.1 |
| Per-client chat rate limit behind nginx | 20 requests from one client → 21st gets 429; a second client immediately gets 200 |
| Request size limit (Kestrel) | 70 KB body to `/api/chat` → 413 |
| Screenshots | Captured by `scripts/screenshots` from the running stack (demo mode) |

### 1.1 Failure scenarios (running stack)

| Scenario | Observed behaviour |
|---|---|
| SQL Server stopped | Chat: "The analytics API is unavailable…" (HTTP 200, no tool calls). Dashboard endpoints: **503** problem details (was an opaque 500 before this audit) |
| AI service stopped | `/api/chat` → **503** "The AI service is unavailable." |
| .NET API stopped | AI service answers "The analytics API is unavailable…" with no tool calls |
| All tools fail (500) | "I could not retrieve the data needed…"; no findings; tool calls marked `failed` (automated test) |
| One of four tools fails | Answer built from the three that succeeded; the failed call is shown (automated test) |
| Model unavailable / no credentials / refusal / timeout | Falls back to the deterministic pipeline and says so in `warnings` (automated tests with a fake SDK client) |

## 2. Unverified

| Item | Status |
|---|---|
| **Live answers from the Anthropic API** | **Unverified.** No `ANTHROPIC_API_KEY` or `ant` profile was available. The provider's request shape, tool-result loop, structured-output parsing, refusal and error handling, deadlines and history handling are tested against a fake SDK client only. `tests/ai/test_live_llm.py` covers the acceptance question, a multi-step question, an unsupported question, missing data, tool failure and prompt injection with real calls; it is skipped until a key is set. |
| Answer quality of the live model | Unverified (depends on the item above). Grounding guarantees provenance of numbers, not the quality of the explanation. |
| Non-UTC plant time zones end to end | The C# clock is unit-tested with Europe/Berlin (DST), but the oracle and the demo dataset are UTC-only. |
| Behaviour under concurrent load | Not tested. The rate limiter is in-memory and per process. |
| .NET line coverage | Not measured (no coverage collector configured). Python AI service coverage was measured: **95% of lines**. |
| Frontend behaviour in CI | Unit tests only; UI flows were verified manually in a browser and via the screenshot script, not by an automated end-to-end suite. |

### 2.1 What the demo (deterministic) provider proves and does not prove

It runs the same graph, tools, data and grounding check as live mode, so it verifies the orchestration,
limits, failure handling and evidence pipeline. It does not exercise LLM planning or LLM-written text.

### 2.2 Missing-data and period probes (running stack, after fixes)

| Question | Before the audit | After |
|---|---|---|
| "…most downtime in March 2026?" (no records) | Answered Nov 4–10 instead, no warning | "No data is available for Mar 1 – Mar 31, 2026…"; warning names the covered range; no chart |
| "…in September 2026?" | Answered Nov 4–10 instead | Sep 1–30 queried; Line 04, 3,975 min |
| "from 2026-10-01 to 2026-10-07" | Answered Nov 4–10 instead | Oct 1–7 queried |
| "…next week?" (forecast) | Answered Nov 4–10 as if it were the forecast | Declined: no forecasting; no tool calls |
| "from 2026-08-01 to 2026-08-31" (partial data) | — | Answered, with a warning that records cover only part of the window |

## 3. Tests executed

| Suite | Command | Result |
|---|---|---|
| Dataset + metric oracle | `python -m unittest discover -s tests/data -t .` | **23 passed** |
| .NET unit + integration (Testcontainers SQL Server) | `dotnet test OpsPilot.sln` | **93 passed**, 0 failed |
| AI service | `python -m pytest tests/ai` | **98 passed**, 6 skipped. The skipped tests are `test_live_llm.py` and need an API key. The 2 live-API contract tests ran against the running stack and passed. |
| Web | `npm test` | **13 passed** |
| Python coverage (AI service) | `coverage run -m pytest tests/ai` | 95% of 1,112 statements |
| GitHub Actions | push to `main` | Recorded in section 9 once the run completes |

New tests added in this audit:
- grounding regressions;
- period parsing;
- missing and partial data;
- citations to unknown tool calls;
- model refusal text;
- the token budget at answer time;
- request deadlines;
- history handling;
- disabling live mode;
- conversation and body size limits;
- database outage mapping;
- a live LLM suite, gated on an API key.

## 4. Security review

### 4.1 Architecture: holds up

- **The model cannot reach the database:**
  - The AI service has no database credentials.
  - Tools are fixed, parameterized LINQ queries behind an allowlist.
  - Arguments are validated twice: Pydantic first, then .NET, which is authoritative.
  - Every request uses a `db_datareader`-only login.
- **Service authentication:**
  - Both services refuse every request when no key is configured.
  - Both compare keys in constant time.
- **Internal endpoints** are not routable from the browser origin. Every port binds to `127.0.0.1`.
- **Tool output as an injection path:** only seeded line and reason names reach the model, as JSON inside
  `tool_result` blocks. Free-text event descriptions are never returned. Answers are rendered as text by
  React; there is no `dangerouslySetInnerHTML`.
- **No secrets** are in the repository or its history (scanned before publishing). Logs contain no questions
  and no secrets.

### 4.2 Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| C1 | Critical (correctness) | Demo mode ignored explicit periods (months, ISO dates, "next week") and silently answered the last 7 days | **Fixed:** explicit periods are parsed; unsupported or ambiguous periods and forecasts are declined; never a silent default |
| H1 | High | Grounding: case-insensitive month prefixes (`Dec[a-z]*`) treated "declined", "decreased", "may" as dates and **removed the following number from the check**; "Output decreased 2500 units" passed as verified | **Fixed:** exact, case-sensitive month names with a valid day; regression tests |
| H2 | High | Grounding: "difference of any two values" accepted 66% of random integers 1–1000 on a typical 3-result answer | **Fixed:** differences only within the same field path and only for small fields (≤ 6 values); measured 9.1% (3 results) / 4.4% (1 result), and the remaining acceptance is almost entirely exact coincidences with cited values |
| H3 | High (dependency) | `react-router-dom` 6.28.0 in the production bundle: open-redirect/XSS advisories | **Fixed:** 6.30.6; also vite 5.4.21, vitest 2.1.9, postcss 8.5.32 (dev); `npm audit`: 0 |
| M1 | Medium | A finding citing non-existent tool-call IDs was checked against *all* evidence and shown as backed by every call | **Fixed:** numbers must come from the cited results; numeric findings citing nothing are removed |
| M2 | Medium | Chat rate limit keyed on the nginx container's address, i.e. one global bucket | **Fixed:** forwarded headers from private networks only (one hop); nginx overwrites `X-Forwarded-For`; verified per-client buckets |
| M3 | Medium (cost) | Any browser could select paid live mode; the answer call was not budgeted; history up to ~80k chars was re-sent | **Fixed:** live mode only if `OPSPILOT_ALLOW_LIVE=true`; budget checked before the answer call; conversation capped at 16,000 chars (API and AI service) |
| M4 | Medium | Model calls were not bounded by the request deadline (up to 3 × 40 s), so a slow call discarded all gathered evidence with a 504 | **Fixed:** every call gets `timeout = remaining − reserve`, one SDK retry; on timeout the deterministic pipeline answers from the evidence |
| M5 | Medium (correctness) | A window without records was reported as "0 minutes of downtime"; partial coverage was silent | **Fixed:** results are marked `full/partial/none` against the dataset range; "none" is reported as no data (also visible to the model); partial gets a warning |
| M6 | Medium | Database outage returned an opaque 500 from dashboard endpoints | **Fixed:** 503 problem details |
| L1 | Low | Live mode replaced the model's correct "I can't answer that" with "no tool was called" | **Fixed:** the model's text is shown, after the grounding check |
| L2 | Low | Browser-supplied history was passed to the model as real assistant turns (forgeable) | **Fixed:** earlier turns are passed as quoted, untrusted context inside a user message; the question is JSON-encoded in prompts |
| L3 | Low | Reader login/password over 128 chars made `QUOTENAME` return NULL and provisioning silently skip | **Fixed:** length check with a clear error |
| L4 | Low | No API-level body limit (only nginx's) | **Fixed:** 64 KB `RequestSizeLimit` on `/api/chat` (413 verified on Kestrel) |
| L5 | Low (test only) | SSH.NET advisory via Testcontainers 4.1.0 | **Fixed:** Testcontainers 4.16.0; `dotnet list package --vulnerable`: none |
| L6 | Low | One shared service key for both directions (API→AI, AI→API) | **Open:** split into two keys before deployment |
| — | Not a bug | AI service returned no JSON during an outage test | Caused by the test sequence (the service was restarting); re-run returned the expected JSON |

## 5. Bugs discovered and fixed (summary)

C1, H1, H2, H3, M1–M6, L1–L5 above. Seven of these came from the independent review: H1, H2, M1–M4 and
L1–L3. C1 and M6 were found by runtime probing. H3 and L5 were found by dependency scans. Every fix has an
automated regression test, except the nginx and forwarded-header behaviour, which was verified at runtime and
whose unit-testability is limited by TestServer.

## 6. Code quality

- **Boundaries are clean.**
  - The web app only knows `/api`.
  - The API is the only data owner.
  - The agent depends on two interfaces: the `ToolClient` and the `Provider` protocol.
  - Metric arithmetic is pure and unit-tested in C#, and mirrored by the oracle.
- **Intentional duplication:**
  - Metric formulas exist in C# and Python, so that each can check the other through the 29 golden cases.
  - Tool argument schemas are defined in C# and Python, checked against each other by a contract test.
- **Complexity hotspots:**
  - `providers/deterministic.py` (342 statements of rules and templates) exists only for demo mode. It is
    the code most likely to drift as questions grow; it should stay a demo, not become an NLU engine.
  - `agent.py` keeps the graph in one function for readability; nodes are small.
- **Cleaned up in this audit:**
  - The `_validated` attribute hack in the agent was replaced by a state counter.
  - A deprecated Testcontainers API was replaced.
- **Remaining nits:** date-range labels are formatted in two places (`charts._period`, `Period.label`).

## 7. Remaining technical risks

1. **Live LLM path not verified against the real API** (section 2). This is the top priority.
2. **The grounding check is lexical.** It proves a number appears in cited evidence. It does not prove the
   sentence uses it correctly, and it cannot tell a hypothesis written as a calculation from a real one. A
   fabricated number that equals some cited value still passes (≈4–9% of random integers in typical answers).
3. **No authentication or authorization.** This is acceptable only for localhost with synthetic data. Separately:
   - `X-Forwarded-For` can be spoofed by anyone who can reach the API port directly, which today means localhost only.
   - The rate limiter is in-memory and does not scale out.
4. **Demo-mode coverage is a fixed set of question shapes.** Anything else is declined, honestly, but it limits the demo.
5. **Build reproducibility:**
   - `requirements.lock` has no hashes.
   - The SQL Server image uses the `2022-latest` tag.
6. **Migrations run as `sa`** in the local Compose setup. Production needs a dedicated migration principal.

## 8. Recommended next priorities

**Before Phase 2:**
- Run `tests/ai/test_live_llm.py` with a real key.
- Record the results here.
- Fix whatever it finds.

Everything else is in the Phase 2 roadmap below.

### Phase 2 roadmap (ordered by engineering value, not visual impact)

1. **Evaluation harness first.** Turn the golden cases into a versioned question set with expected tool calls,
   expected arguments and expected numbers. Score live runs on four things:
   - tool selection,
   - argument validity,
   - numeric accuracy (via the oracle),
   - grounding pass rate, plus refusals for unsupported and injection cases.

   Keep deterministic assertions separate from any model-graded checks. Every later change gets measured against it.
2. **Observability.** Add OpenTelemetry traces and spans:
   - per request, graph node, tool call and model call;
   - token and latency metrics;
   - correlation IDs across web → API → agent;
   - an Agent Activity page that reads the traces, rather than a second, invented store.
3. **Semantic grounding.** Have the model declare operands for derived numbers (`{"value": 3.3, "from":
   ["tc1.totals.attainment_pct", "tc2.totals.attainment_pct"], "op": "diff"}`) and recompute them in code.
   This closes the coincidence gap in risk 2.
4. **Agent reliability.**
   - Streaming progress (server-sent events) for the timeline.
   - Idempotent retries for transient tool failures.
   - A per-request trace ID returned to the UI.
   - Explicit handling of contradictory evidence across tools.
5. **More tools, each with schema, limits, oracle cases and contract tests:**
   - `get_quality_issues`,
   - `get_equipment_incidents`,
   - `compare_production_lines`.
6. **Security hardening for any shared deployment:**
   - authentication (OIDC) and per-user rate limits,
   - separate service keys,
   - a dedicated migration principal,
   - pinned images,
   - hashed Python locks.
7. **RAG (Phase 3)** after the above, so that retrieval quality is measured by the same evaluation harness from day one.

## 9. CI

Pending: updated with the run for this commit.
