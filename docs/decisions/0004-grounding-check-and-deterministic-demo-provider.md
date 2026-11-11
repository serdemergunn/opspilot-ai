# ADR 0004 — Code-enforced grounding and a deterministic demo provider

Status: Accepted · 2026-11-11

## Context

Prompt instructions ("do not invent numbers") reduce hallucination but cannot guarantee it. Reviewers
also need to run the agent without a paid API key, and demo output must not be passed off as model output.

## Decision

1. **The model participates in exactly two steps**: proposing tool calls (`plan`) and writing the answer
   (`compose`). Tool existence, argument validation, budgets, execution, charts and verification are code.
2. **Grounding check after every answer.** Each finding must cite tool calls; every number in it must equal
   a value in those results at the precision written, or (except for measurements) the absolute difference
   of two values of the same field when that field has at most six values (two periods' totals, or lines
   compared side by side). Dates, line names, error codes and roadmap references are not quantities; month
   names are matched case-sensitively as whole words. Failing findings are removed and a warning explains why;
   an unverifiable summary is withheld. *(Tightened in the Phase 1 audit: the first version accepted
   differences of any two values and treated words such as "declined" as dates.)*
3. **Demo mode is a provider, not a separate path.** `DeterministicProvider` plans with rules and writes
   with templates, through the same graph, tools and grounding check. Responses carry `mode: "demo"` and
   `provider: "deterministic"`. The live provider degrades to it (with a warning) when the model is
   unavailable.

## Consequences

- A fabricated figure cannot reach the user as a finding; at worst a finding is dropped.
- The check is lexical: it verifies that numbers come from evidence, not that the sentence interprets them
  correctly. Kind labels (`hypothesis` vs `calculation`) remain the model's responsibility and are covered
  by evaluation (Phase 4).
- Demo mode covers a fixed set of question shapes; it is a faithful demonstration of the pipeline, not a
  substitute for the model.
