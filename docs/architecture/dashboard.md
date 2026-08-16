# Dashboard architecture

## Purpose

Stage 9 turns the existing monitoring domain and query APIs into the primary
operator experience. The dashboard must remain a client of the same versioned
FastAPI management APIs that future automation uses; it must not introduce
frontend-only persistence or hidden configuration semantics.

## Scope

The dashboard is the Next.js 16 application under `frontend/`. It owns the V1
operator workflows for:

- agents and agent groups;
- targets and target groups;
- monitors and monitor assignments;
- current health and recent execution state;
- historical probe measurements;
- SmokePing-style ICMP latency distributions and packet loss; and
- probe-specific HTTP, TCP, DNS and TLS detail views.

Authentication and account-security management remain in `auth-frontend/`.
Browser authentication continues to use the shared opaque Redis session.

## Application structure

The App Router is used throughout. Authenticated routes share a server-rendered
application shell containing realm context, navigation and account links.
Initial page data should be loaded in server components using the existing
session cookie and FastAPI. Client components are reserved for interactive
forms, filters, dialogs and visualizations that require browser state.

The dashboard must not copy authorization rules from the backend. UI controls
may be hidden or disabled when the current realm role clearly lacks a capability,
but FastAPI remains authoritative and every mutation must handle a rejected
request safely.

## Management workflows

V1 configuration must be possible without editing files. Management pages cover
agents, groups, targets, monitors and assignments and use the existing
realm-scoped `/api/v1/monitoring/*` endpoints.

Mutations should use server actions or route handlers that forward the current
session cookie to FastAPI. They must:

- preserve FastAPI validation and authorization behavior;
- return useful structured errors to the initiating form;
- revalidate affected dashboard routes after successful writes;
- never expose write-only secrets after their intended one-time display; and
- avoid optimistic state that could imply a configuration change was accepted
  when the API rejected it.

Agent enrolment tokens are one-time sensitive values. A newly issued token may
be shown immediately to the operator, but must not be persisted in frontend
state beyond the workflow or become retrievable through ordinary reads.

## Query and visualization model

Historical views are driven by realm-scoped backend query APIs. Missing
observations are represented as gaps; the frontend must never interpolate a
missing observation into a successful zero-latency or zero-loss sample.

ICMP visualization preserves the distribution data stored for each observation.
The SmokePing-style graph should use individual RTT samples to render latency
density/range while showing packet loss separately. Median or percentile lines
may be added as summaries but must not replace the distribution.

Cross-agent comparison uses `agent_id` as a first-class series dimension.
Time-range controls use explicit start/end values and must respect backend range
limits. Later aggregation APIs may reduce payload size for long ranges without
changing the semantic distinction between measured values and missing data.

Probe-specific views expose the typed measurements already stored for HTTP,
TCP, DNS and TLS rather than flattening results into generic JSON in the UI.

## Current-state semantics

The interface must distinguish at least:

- target/probe unhealthy: an observation completed and assessed unhealthy;
- execution failure: the probe could not produce a normal target assessment;
- agent offline: heartbeat state says the monitoring vantage point is offline;
- missing data: no observation exists for the expected period; and
- disabled or unassigned configuration: monitoring is intentionally not
  expected.

These states must not be collapsed into a single red/green boolean.

## Frontend contracts

TypeScript remains strict. API response and request shapes should live in a
small typed frontend API layer rather than being re-declared independently on
each page. Avoid `any`; probe configuration editors should use discriminated
probe-type models as they become interactive.

The frontend API layer is intentionally thin. It may normalize transport errors
for presentation, but it must not reinterpret backend domain rules.

## Accessibility and responsive behavior

Management forms, navigation, tables and graphs must remain keyboard usable.
Status must not be communicated by color alone. Empty, loading, failure and
missing-data states require explicit text. Responsive layouts should preserve
all management operations rather than hiding them on small screens.

## Testing

Stage 9 introduces component/unit testing for meaningful frontend behavior in
addition to TypeScript, ESLint, Prettier, Stylelint and production builds.
Tests should cover management-form validation/error handling, navigation and
state rendering, plus visualization behavior such as missing-data gaps and
cross-agent series separation.

Backend integration tests remain responsible for tenancy, authorization and
durable management-domain behavior.
