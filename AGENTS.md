# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project

BifrostNMS is a modern distributed Network Monitoring System consisting of a FastAPI control plane, separate Next.js 16 authentication and dashboard applications, and lightweight Go agents deployed at monitoring vantage points.

## Architectural priorities

1. Design persistent domain models deliberately before building features that depend on them.
2. Realm tenancy is fundamental. Persistent realm-owned data must have an explicit, reviewable tenancy boundary.
3. Keep agents self-contained, reliable and portable. Native Go implementations are the default for ICMP, DNS, HTTP, TCP, TLS, traceroute and other probes.
4. Requiring external command-line tools such as `fping`, `dig`, `curl` or `traceroute` is exceptional and requires explicit architectural justification.
5. Agents must continue operating during control-plane/network outages and will use local SQLite for configuration state and unsynchronised observations.
6. PostgreSQL/TimescaleDB stores persistent application and monitoring data. Redis stores browser sessions and appropriate ephemeral state.
7. Prefer explicit typed APIs/contracts between backend, frontends and agent.
8. Design for known future requirements without implementing speculative distributed complexity early.

## Stack

- Backend: Python 3.12+, FastAPI, Tortoise ORM, Pydantic.
- Persistent database: PostgreSQL with TimescaleDB for monitoring time-series data.
- Ephemeral/session store: Redis.
- Agent: Go, with SQLite for durable local operation/offline sync.
- Auth frontend: Next.js 16, React 19, TypeScript, App Router.
- Dashboard frontend: Next.js 16, React 19, TypeScript, App Router.
- Tooling: repository `tools/` suite, Ruff, mypy, pytest, ESLint, Prettier, Stylelint, gofmt, go vet and go test.

Do not introduce Django or replace Tortoise ORM without an explicit architectural decision.

## Authentication

Authentication is a first-class subsystem, not a later add-on. Passwords, TOTP/recovery codes and WebAuthn/passkeys are supported from the initial architecture. Browser sessions are opaque tokens stored in Redis; the raw session token must never be stored in PostgreSQL or logged. Use established security libraries rather than implementing cryptographic primitives manually.

Read `docs/architecture/authentication.md` before changing authentication behaviour.

## Database changes

Use Tortoise's built-in migration system. Do not use `generate_schemas()` as a substitute for migrations and do not introduce Aerich. After changing persistent models, create and review a migration using `tools/db-makemigrations`, then apply it with `tools/db-migrate`.

Read `docs/development/database-migrations.md` before changing schemas.

## Working rules

Read nearby code/tests/docs before editing. Keep changes scoped. Add tests for behaviour. Do not silently weaken lint/type/test rules. Do not commit secrets, credentials, local environment files or generated coverage output.

Run `tools/lint` and `tools/test-all` before considering a change complete. If a check cannot run, state exactly why.

For Go, run `gofmt` and keep dependencies minimal. For Python, use modern typing and async APIs. For TypeScript, keep strict typing and avoid `any` unless unavoidable and documented.

## Documentation

Update README/docs when adding a user-visible feature, environment variable, port, deployment requirement, data-store requirement, authentication change or breaking API/configuration change.
