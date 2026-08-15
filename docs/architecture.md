# Architecture

BifrostNMS uses a central FastAPI control plane and independently deployable Go
agents. The server owns desired configuration, identity, authorization, durable
ingestion and query APIs. Agents own probe scheduling and execution at their
local network vantage points.

The first implementation should favor direct communication between agents and
the server. A new message broker or streaming platform must not be introduced
until workload or reliability requirements demonstrate that it solves a real
problem. Celery and Redis support control-plane background tasks; they are not
the observation transport between agents and the server.

See `PLAN.md` for the product scope, delivery stages and architectural decision
record. Detailed authentication behavior is documented in
`docs/architecture/authentication.md`.

## Components

### Control plane

FastAPI exposes browser, management, agent enrolment, configuration, ingestion
and query APIs. Tortoise ORM maps ordinary relational models to PostgreSQL and
provides migrations. Reviewed direct SQL may be used where TimescaleDB ingestion
or analytics would be poorly served by row-at-a-time ORM operations.

### Agent

The Go agent pulls versioned assigned configuration, schedules native probes
locally and reports structured observations in idempotent batches. SQLite stores
its identity, last valid configuration, scheduling state and unsynchronized
observations so monitoring continues during control-plane outages.

The agent should have a small memory and CPU footprint with minimal runtime
dependencies. Standard probes must not rely on host command-line utilities.

### Web applications

The separate Next.js 16 App Router applications are:

- `auth-frontend/` for login, account and credential security; and
- `frontend/` for monitoring configuration, status and visualization.

Both use strict TypeScript and share the FastAPI/Redis browser-session model.

## Data

- PostgreSQL stores durable identity, tenancy, configuration and operational
  data.
- TimescaleDB stores immutable monitoring observations and measurements.
- Redis stores opaque browser sessions and suitable ephemeral state.
- Agent-local SQLite stores durable offline state and pending observations.

Retention, compression, aggregation and the exact heterogeneous measurement
schema must be designed and documented before monitoring models are implemented.
Realm isolation and the V1 graph query patterns are requirements of that design.
