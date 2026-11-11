# ADR 0001 — Allowlisted, typed tools instead of text-to-SQL

Status: Accepted · 2026-11-11

## Context

The agent must answer operational questions from database records. The most flexible option is
letting the model write SQL. The safest option is a fixed set of typed operations.

## Decision

The model can only call tools from a registry defined in code. Each tool has a JSON schema with
`additionalProperties: false`, bounded parameters (date range ≤ 92 days, `top_n` ≤ 20, ≤ 10 line
codes) and a fixed, parameterized query implemented in the .NET API. No model-generated SQL is
ever executed.

## Consequences

- No SQL injection surface from model output; queries are reviewed, indexed and testable.
- Metric definitions are consistent across answers, dashboard and evaluation.
- Every number in an answer can be traced to a tool call with known semantics.
- Less flexible: an unanticipated question gets "not supported yet" instead of an improvised
  query. We accept that; new questions become new tools, with tests.
