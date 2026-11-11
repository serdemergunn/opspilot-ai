# ADR 0002 — The .NET API is the gateway and the tool authority

Status: Accepted · 2026-11-11

## Context

Three applications (web, API, AI service) need clear boundaries. The AI service processes
untrusted text (user messages, later retrieved documents), so it should hold as little privilege
as possible.

## Decision

- The browser talks only to the .NET API. `/api/chat` is proxied to the AI service, which is not
  exposed outside the Compose network.
- The .NET API is the only component with database credentials. Analytics queries use a
  read-only SQL login.
- Agent tools in the AI service are typed HTTP clients for `POST /internal/tools/{name}`,
  authenticated with a service key. Arguments are validated twice: Pydantic in the AI service
  (to give the model fast, specific feedback) and in .NET (authoritative).

## Consequences

- One place for authentication, rate limiting and data access rules.
- A compromised or confused agent can only call read-only, bounded endpoints.
- A call loop exists (API → AI service → API). It is internal and acceptable; the tool endpoints
  do not proxy back to the AI service, so there is no recursion.
- Some duplication of argument schemas across C# and Python. Mitigated by a contract test that
  compares the JSON schemas both sides publish.
