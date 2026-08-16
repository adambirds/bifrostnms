# BifrostNMS

**A modern, lightweight, distributed Network Monitoring System.**

> See your network from everywhere.

BifrostNMS is an open-source network monitoring platform inspired by the distributed monitoring model that made SmokePing so useful, rebuilt around a modern API, dedicated authentication application, monitoring dashboard, public documentation website, and lightweight Go agents.

## Architecture

```text
Next.js 16 Public Website (3002)

Next.js 16 Auth UI (3001) ----+
                              |
Next.js 16 Dashboard (3000) --+--> FastAPI (8000) --> PostgreSQL / TimescaleDB
                              |          |
Go Agents --------------------+          +--> Redis sessions
```

The monorepo contains:

- `backend/` — FastAPI control plane using Tortoise ORM.
- `auth-frontend/` — separate Next.js 16 App Router authentication/security application.
- `frontend/` — Next.js 16 App Router monitoring dashboard.
- `website/` — Next.js 16 App Router public product and documentation website.
- `agent/` — self-contained Go monitoring agent.
- `deploy/` — deployment assets.
- `docs/` — architecture and operational documentation for maintainers and operators.
- `tools/` — shared development, linting and database tooling.

## Core principles

- Agents should implement probes natively in Go. Requiring host utilities such as `fping`, `dig`, `curl`, or `traceroute` should be an exceptional case rather than normal operation.
- Agents will retain configuration and unsynchronised observations locally in SQLite so monitoring continues through control-plane outages.
- Realms are a first-class tenancy boundary from the start. Self-hosted installations may have multiple realms; BifrostNMS Cloud will use the same model at larger scale.
- PostgreSQL/TimescaleDB stores persistent application and monitoring data. Redis stores browser sessions and other appropriate ephemeral state.
- Authentication includes password login, TOTP two-factor authentication with recovery codes, and WebAuthn/passkeys from the beginning.

## Development

Use VS Code Dev Containers and choose **Dev Containers: Reopen in Container**.

For the first database setup:

```bash
./tools/db-bootstrap
```

Start the applications in separate terminals:

```bash
uvicorn backend.bifrostnms.main:app --host 0.0.0.0 --port 8000 --reload
pnpm --dir auth-frontend dev
pnpm --dir frontend dev
pnpm --dir website dev
```

Then visit:

- `http://localhost:3001` for authentication and account security;
- `http://localhost:3000` for the monitoring dashboard; and
- `http://localhost:3002` for the public website and user documentation.

The public website documentation includes the end-to-end local setup workflow covering realms, agents, targets and groups, monitors and assignments, probe results, and local disconnect/reconnect testing.

Documentation:

- `PLAN.md`
- `docs/architecture.md`
- `docs/development/local-development.md`
- `docs/development/database-migrations.md`
- `docs/deployment/overview.md`
- `docs/deployment/timescaledb.md`
- `docs/architecture/authentication.md`
- `website/src/app/docs/` — public user documentation.
- `CONTRIBUTING.md`
- `AGENTS.md`

## Status

BifrostNMS is in early development. APIs and schemas may change before the first stable release.

## Sponsoring

See `SPONSORS.md` for ways to support development.

## License

A project licence will be added before the first public release. Until then, public visibility should not be interpreted as granting rights beyond GitHub's Terms of Service.
