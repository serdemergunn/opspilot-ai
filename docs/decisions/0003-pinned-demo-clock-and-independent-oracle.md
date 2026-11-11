# ADR 0003 — Pinned demo clock and an independent metric oracle

Status: Accepted · 2026-11-11

## Context

Questions like "last week" depend on the current time, but the synthetic dataset ends on a fixed
date. Evaluation also needs expected numbers that do not come from the system under test.

## Decision

1. The dataset is generated deterministically for 90 days ending at `2026-11-11T00:00:00Z`.
   The API resolves relative dates against `OpsPilot:Clock:ReferenceTimeUtc` (Compose: `OPSPILOT_REFERENCE_TIME_UTC`) when set
   (demo, tests, evaluation) and against the wall clock otherwise.
2. A second, deliberately simple implementation of the metric definitions lives in
   `sample-data/reference_metrics.py`: Python standard library only, reading the same CSVs the
   database is seeded from. It produces `sample-data/golden/expected_metrics.json`.
3. The C# implementation must reproduce the golden values exactly (parity test). The agent
   evaluation uses the same oracle to check numeric accuracy of answers.

## Consequences

- Demo answers and evaluation results are stable over time.
- Two independent implementations make a formula bug visible as a parity failure rather than
  a silently wrong chart.
- The cost is maintaining the formulas twice; `docs/architecture/metric-definitions.md` is the
  contract both follow.
