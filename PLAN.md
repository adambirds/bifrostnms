# BifrostNMS project plan

## Purpose

This document preserves the product direction, architectural boundaries and
delivery roadmap for BifrostNMS. It is intended to remain useful to maintainers,
contributors and coding agents even when the original design conversations are
no longer available.

This is an overarching plan, not a substitute for detailed architecture
documents. Decisions about a domain or protocol must be documented under
`docs/architecture/` before implementation when the stage below requires them.

## Product vision

BifrostNMS is an open-source distributed Network Monitoring System inspired by
the distributed monitoring model that made SmokePing useful, rebuilt around a
modern control plane, autonomous lightweight agents and an accessible web
interface.

Operators deploy agents at the network vantage points they care about. Those
agents execute monitoring locally, retain observations during control-plane
outages and synchronize them when connectivity returns. Users configure the
system centrally and compare current and historical behavior across agents.

The project should grow beyond simple uptime checks into distributed network
observability without losing a lightweight, reliable self-hosted experience.
BifrostNMS Cloud may later provide a hosted control plane and public probe
locations using the same fundamental tenancy and agent model.

## Product principles

### Observe from everywhere

The same target must be observable from several independent locations. Results
should make it easy to distinguish a target failure from a problem affecting one
agent, site, provider or network path.

### Preserve the value of SmokePing-style data

BifrostNMS must not reduce latency monitoring to a single average. It should
retain enough information to visualize latency distributions, packet loss,
jitter and outliers using modern interactive versions of SmokePing-style smoke
graphs.

### Keep agents autonomous

The control plane distributes desired configuration; it does not remotely
schedule every probe execution. Agents schedule work locally, persist their last
valid configuration and continue monitoring while disconnected.

### Prefer self-contained native probes

ICMP, HTTP/HTTPS, TCP, DNS, TLS and other normal probes should be implemented in
Go using the standard library or focused Go packages. Requiring external tools
such as `fping`, `curl`, `dig` or `traceroute` is exceptional and requires an
explicit architectural justification.

Specialized integrations such as `iperf3` and user-supplied executable probes
may be supported later when their external dependency is visible and optional.

### Make tenancy fundamental

A realm is the persistent tenant boundary. A self-hosted installation may have
several realms even though most deployments will use one. BifrostNMS Cloud will
use the same model across many customer realms.

Realm ownership must be explicit and reviewable for persistent domain data.
User identity is installation-wide and realm access is expressed through realm
memberships rather than by placing a realm directly on a user.

### Design for automation without requiring it in V1

Normal users should be able to configure BifrostNMS through the web interface,
but no important resource should be manageable only through UI-specific logic.
The UI should use the same versioned management API that future automation can
use.

The architecture must allow future:

- control-plane and agent deployment with Ansible;
- unattended agent enrolment and upgrades;
- realm, agent, target, monitor and alert configuration with Terraform;
- configuration import/export and drift detection; and
- headless installation, migration and administration.

The official Ansible and Terraform integrations are explicitly post-V1 work.
Designing stable identifiers, lifecycle operations and typed APIs for them is
not post-V1 work.

### Add complexity only when it earns its place

Future scale should influence schemas and interfaces where later change would be
destructive. It does not justify premature microservices, message streaming,
database sharding or orchestration requirements.

The initial control plane should remain a cohesive FastAPI application. Agents
communicate with it using direct, versioned APIs and batch operations.

## Authoritative architecture

```text
Next.js public website -------+
                              |
Next.js authentication UI ----+
                              |
Next.js dashboard ------------+----> FastAPI control plane
                              |             |
Distributed Go agents --------+             +--> PostgreSQL/TimescaleDB
     |                                      +--> Redis sessions
     +--> SQLite                            +--> Redis/Celery
```

### Control plane

- FastAPI provides browser, management, enrolment, configuration, ingestion and
  query APIs.
- Tortoise ORM manages ordinary persistent relational models and migrations.
- Direct, reviewed SQL may be used where TimescaleDB ingestion or analytics
  would be poorly served by row-at-a-time ORM operations. Request-derived values
  must remain database parameters rather than being interpolated into query text.
- The control plane owns desired configuration, identity, authorization,
  durable ingestion and query behavior.

### Persistent and ephemeral storage

- PostgreSQL stores durable identity, tenancy, configuration and operational
  data.
- TimescaleDB stores monitoring time series and supports later retention,
  compression and continuous aggregation policies.
- Redis stores opaque browser sessions and appropriate ephemeral state.
- Redis also provides the Celery broker and result backend using databases that
  are separate from browser sessions.

### Web applications

- `auth-frontend/` is the Next.js 16 identity and account-security application.
- `frontend/` is the Next.js 16 monitoring dashboard.
- `website/` is the Next.js 16 public product and end-user documentation site.
- All applications use strict TypeScript and the App Router.
- Authentication and the dashboard remain separately deployable while sharing
  the FastAPI and Redis session model; the public website does not require an
  authenticated browser session for its documentation routes.

### Agent

- The agent is a small portable Go application.
- It pulls versioned desired configuration and schedules probes locally.
- SQLite stores identity, configuration, scheduling state, pending observations
  and synchronization state.
- Observations receive client-generated stable identifiers so retrying an upload
  is safe.
- Uploads are batched, acknowledged and idempotent.
- Synchronized local data is cleaned up according to an explicit retention
  policy rather than deleted speculatively.

### Background work

- Celery handles email, notifications and other suitable asynchronous control-
  plane work.
- Tasks must be idempotent because late acknowledgement permits redelivery.
- Celery is not part of the agent-to-control-plane observation transport.
- A new broker or streaming platform must solve a demonstrated requirement.

## Core domain vocabulary

Names may be refined during domain design, but implementations must preserve the
distinctions below.

### Installation

One deployed BifrostNMS control plane and its supporting services.

### Realm

The tenant and authorization boundary containing monitoring configuration and
observations. Installation superusers are separate from realm roles.

### Agent

An enrolled monitoring process operating at a particular network vantage point.
An agent reports its version, platform, architecture and supported capabilities.

### Agent group

A hierarchical, realm-owned collection of agents used for organization and
group-based monitor assignment. Agents may belong to several groups.

### Target

A reusable destination to observe, identified by a hostname or IP address. A
target is not itself a schedule or probe definition; URL paths, ports and other
probe-specific behavior belong to monitors.

### Target group

A hierarchical, realm-owned collection used to organize targets for navigation,
dashboards and explicit bulk operations. Membership does not silently create or
alter monitors.

### Monitor

A realm-owned definition combining a target, probe type, interval, timeout and
validated probe-specific configuration.

### Monitor assignment

An explicit direct-agent or agent-group relationship that determines which
agents execute a monitor. Effective assignments are deduplicated, and the
relationship model must support future overrides without duplicating monitors.

### Probe execution or observation

One scheduled execution of a monitor by an agent, including timing, outcome and
diagnostic context.

### Measurement

Structured time-series values produced by an observation. The final schema must
support efficient cross-agent queries and probe-specific data without collapsing
everything into an unvalidated JSON value.

## Cross-cutting requirements

### API and automation compatibility

Management APIs should provide:

- explicit stable resource identifiers;
- documented versioning and compatibility behavior;
- idempotent lifecycle operations where practical;
- pagination and deterministic filtering;
- typed request and response contracts;
- structured machine-readable validation errors;
- separation of write-only secrets from readable state; and
- behavior suitable for Terraform refresh, plan and drift detection.

### Security

- Raw browser session tokens must never be stored in PostgreSQL or logged.
- Passwords use established password-hashing libraries and Argon2.
- TOTP secrets are encrypted at rest and recovery codes are stored as hashes.
- WebAuthn ceremony and cryptographic validation use established libraries.
- Agent credentials must be revocable and safely provisioned.
- Realm access must be enforced at query and mutation boundaries.
- Secrets must never be returned merely to make declarative automation easier.

### Reliability

- Monitoring continues during control-plane and network outages.
- Synchronization retries do not duplicate accepted observations.
- Invalid configuration must not replace an agent's last valid configuration.
- Probe execution uses deadlines and bounded concurrency.
- Backpressure and local-storage limits must fail visibly and predictably.

### Testing and quality

- Python remains fully typed under the repository's strict mypy policy.
- TypeScript remains strict and avoids undocumented `any`.
- Go code is formatted and vetted through `tools/lint`.
- Behavioral changes receive tests at the appropriate unit, integration or
  protocol boundary.
- `tools/lint` and `tools/test-all` must pass before a stage deliverable is
  considered validated.

### Documentation

New protocols, persistent models, operational requirements and user-visible
configuration require documentation. API contracts and configuration examples
must describe behavior rather than relying on the UI as documentation.

## V1 definition

V1 is complete when an operator can:

1. Deploy a control plane and create an installation administrator.
2. Create and use a realm with correctly isolated monitoring data.
3. Enrol multiple agents at different network vantage points.
4. Configure targets, monitors and agent assignments through the web UI.
5. Run the V1 native probe set on the assigned agents.
6. Continue executing probes and storing observations while disconnected.
7. Synchronize the backlog safely when connectivity returns.
8. View current state and historical results across agents.
9. Explore SmokePing-style latency-distribution and packet-loss graphs.
10. Operate the supported deployment with documented backup, migration and
    upgrade procedures.

### V1 native probe set

#### ICMP

- Individual round-trip samples where available.
- Sent and received counts and packet-loss percentage.
- Minimum, average, median and maximum latency.
- Percentiles and a documented jitter calculation.
- IPv4 and IPv6 behavior defined explicitly.

#### HTTP/HTTPS

- Connection and request success.
- HTTP status code and response size.
- DNS, connection, TLS, time-to-first-byte and total duration where available.
- Configurable method, timeout and redirect behavior.
- Basic expected-status and response assertions.
- HTTPS uses the same probe family with TLS-specific measurements.

#### TCP connect

- Connection success or categorized failure.
- Connection duration and timeout.
- IPv4 and IPv6 behavior defined explicitly.

#### DNS

- Explicit resolver, name and record type.
- Query duration, response code and returned records.
- Basic expected-record assertions.
- At least the common A, AAAA, CNAME, MX, NS, TXT and PTR types, subject to the
  detailed probe design.

#### TLS certificate

- Handshake and hostname-validation outcome.
- Subject, issuer and validity period.
- Remaining validity and configurable expiry thresholds.
- Useful categorization of expired, untrusted and hostname-mismatch failures.

### V1 visualization

V1 must include more than summary cards and average lines. At minimum it needs:

- latency-distribution smoke graphs;
- packet-loss visualization;
- selectable time ranges;
- per-agent series and cross-agent comparison;
- summary statistics and recent state;
- clear gaps for missing data rather than fabricated continuity; and
- a useful distinction between probe failure, agent outage and missing data.

### V1 non-goals

The following are not required for V1:

- traceroute, MTR and route-history analysis;
- SNMP, flow collection or network-device management;
- bandwidth testing and `iperf3` integration;
- custom executable probes;
- public status pages;
- SAML or enterprise SSO;
- billing and subscription management;
- hosted public probe locations;
- Kubernetes operators;
- an official Terraform provider;
- an official Ansible role or collection; and
- automated or AI-generated incident diagnosis.

These exclusions do not permit schemas or APIs that make the capabilities
unnecessarily destructive to add later.

## Status model

Each stage uses one of these states:

- **Not started**: no dependable implementation exists.
- **In progress**: design or implementation exists but acceptance criteria are
  incomplete.
- **Implemented**: the planned behavior exists locally but has not completed all
  required validation and documentation.
- **Validated**: acceptance criteria, tests, documentation and CI are complete.

Scaffolding, placeholder routes and empty packages do not make a stage
implemented. A stage may remain in progress while later foundational work begins
when dependencies permit it.

## Delivery stages

### Stage 0: Architecture and domain specification

**Status: Validated**

Objective: settle the durable boundaries before building monitoring features
that depend on them.

Deliverables:

- authoritative component architecture;
- tenancy and authorization design;
- monitoring-domain model and relationship diagram;
- TimescaleDB observation/measurement schema decision;
- agent protocol and enrolment specification;
- agent SQLite and synchronization specification;
- probe contract and result-envelope specification; and
- retention, aggregation and deletion principles.

Acceptance criteria:

- Detailed documents exist under `docs/architecture/`.
- Realm ownership is explicit for every proposed persistent entity.
- Server and local-agent schemas define stable identities and idempotency.
- V1 query patterns have been considered in the time-series design.
- Open questions are recorded rather than silently resolved in code.

### Stage 1: Identity, authentication and realm tenancy

**Status: Validated**

Objective: provide secure identity and realm selection as a foundation for every
management and monitoring API.

Current foundation includes password authentication, Redis sessions, realm
memberships, installation superusers, TOTP/recovery codes, WebAuthn/passkeys and
the separate authentication frontend.

Realm authorization boundaries, audit requirements, production authentication
deployment guidance, email verification and password-reset flows are
implemented and validated.

Acceptance criteria:

- Authentication behavior is documented and covered by security-focused tests.
- Realm switching and all realm-owned access enforce membership or explicit
  installation-superuser authority.
- Account recovery and credential-management flows are complete.
- Production cookie, proxy, HTTPS, Redis and WebAuthn settings are documented.

### Stage 2: Operational foundations

**Status: Validated**

Objective: provide repeatable development, testing, background work, email and
deployment foundations without coupling them to unfinished monitoring domains.

Current foundation includes component CI, repository-wide lint/test commands,
Celery queues, SMTP, Microsoft Graph email and initial Docker images.

Development and backend CI now use a pinned TimescaleDB image, CI applies the
complete migration chain, and supported service, persistence, secret, backup and
upgrade boundaries are documented. Updated container CI validates the clean
database bootstrap plus every supported application image and security scan.

Acceptance criteria:

- Development bootstrap is repeatable from a clean checkout.
- All supported images build and pass security scans in CI.
- Database migration, Celery and email procedures are documented.
- Transactional email services required by authentication are implemented.
- Deployment secrets and persistent volumes are documented.

### Stage 3: Monitoring domain models

**Status: Validated**

Objective: implement the approved realm-owned agents, groups, targets, monitors
and assignments plus the approved TimescaleDB schema.

The realm-owned relational domain, strict V1 probe configuration contracts,
hierarchical groups, memberships and assignments are implemented behind
realm-scoped management APIs. PostgreSQL constraints protect hierarchy,
uniqueness and revision invariants, while TimescaleDB stores common observations
and typed ICMP, HTTP, TCP, DNS and TLS results in seven-day hypertable chunks.
Integration tests exercise the real database schema, archival behavior,
cross-realm rejection and representative realm-led graph query plans.

Deliverables:

- Tortoise models and reviewed migrations;
- typed management schemas and services;
- hierarchical agent/target groups and explicit memberships;
- direct and agent-group monitor assignments;
- TimescaleDB hypertables and required indexes;
- uniqueness, deletion and historical-reference behavior; and
- realm-isolation and model-behavior tests.

Acceptance criteria:

- Models match the Stage 0 design documents.
- Deleting or changing configuration cannot corrupt historical observations.
- Every management query is explicitly realm-scoped.
- Expected ingestion and graph queries have suitable indexes and explain plans.

### Stage 4: Agent enrolment and protocol

**Status: Validated**

Objective: securely establish agent identity and exchange versioned desired
configuration and capability information.

Agents enrol using short-lived, single-use tokens and receive opaque,
individually revocable credentials whose secrets are stored only as digests.
The V1 protocol now provides bounded capability and heartbeat reporting,
derived online status, deterministic immutable configuration snapshots,
conditional retrieval and idempotent activation acknowledgement. Shared JSON
contracts are validated by both the Python control plane and native Go types.

Deliverables:

- one-time or otherwise safely bounded enrolment mechanism;
- issued, revocable agent credentials;
- heartbeat/status protocol;
- versioned configuration retrieval;
- agent capability reporting; and
- typed Go and Python representations with contract tests.

Acceptance criteria:

- Enrolment is usable interactively and by future unattended deployment.
- Credentials are never exposed again through ordinary read APIs.
- Revoked or cross-realm agents cannot retrieve configuration or upload data.
- Protocol compatibility and upgrade behavior are documented.

### Stage 5: Agent SQLite storage and synchronization

**Status: Validated**

Objective: make the agent durably autonomous during control-plane outages.

Deliverables:

- versioned local SQLite schema and migrations;
- durable identity and last-valid-configuration storage;
- pending-observation queue;
- batched upload and acknowledgement protocol;
- retry, backoff, deduplication and cleanup behavior; and
- bounded-storage failure policy.

Acceptance criteria:

- Restarting an agent loses neither accepted configuration nor pending data.
- Invalid new configuration leaves the last valid version active.
- Repeated batches do not duplicate server observations.
- Simulated outages and reconnection are covered by integration tests.

### Stage 6: Native Go probe framework

**Status: Validated**

Objective: provide a typed, testable and extensible execution framework shared
by all V1 probes.

Deliverables:

- probe interface and typed configuration validation;
- scheduler with deadlines and bounded concurrency;
- normalized execution/result envelope;
- capability detection;
- cancellation and shutdown behavior; and
- deterministic test facilities.

Acceptance criteria:

- Adding a probe does not require changes to unrelated probe implementations.
- Bad configuration is rejected before scheduling.
- Hung probes cannot block the scheduler indefinitely.
- Resource limits and error categories are documented and tested.

### Stage 7: ICMP monitoring

**Status: Validated**

Objective: complete the first end-to-end monitoring path using native Go ICMP.

Deliverables:

- native ICMP implementation;
- Linux privilege/capability deployment behavior;
- distribution-preserving result model;
- ingestion and historical query APIs; and
- basic dashboard visibility sufficient to validate the full path.

Acceptance criteria:

- Multiple agents can execute the same monitor independently.
- Packet loss and individual successful RTT values survive synchronization.
- IPv4/IPv6, timeout, permission and unreachable behavior are tested.
- No `ping` or `fping` executable is required.

### Stage 8: HTTP/HTTPS, TCP, DNS and TLS monitoring

**Status: Validated**

Objective: complete the useful baseline synthetic-monitoring probe set using
native Go implementations.

HTTP/HTTPS, TCP, DNS and TLS are implemented as native Go probes and share the
common observation envelope, typed probe-specific measurements, configuration
validation and categorized error behavior. Deterministic local protocol fixtures
cover success, timeout, assertion and representative DNS/TLS failure paths without
requiring public Internet services or external command-line probe dependencies.

Acceptance criteria:

- Every V1 probe emits the common observation envelope and typed probe-specific
  measurements.
- Probe configuration is validated consistently in the API and agent.
- Timeouts, DNS errors, TLS errors and assertion failures remain distinguishable.
- Standard operation requires no external command-line probe dependencies.
- Unit tests use deterministic local servers or protocol fixtures rather than
  relying on public Internet services.

### Stage 9: Dashboard and SmokePing-style visualization

**Status: Validated**

Objective: make distributed measurements understandable and useful to operators.

The dashboard now provides the complete V1 management workflow for agents,
groups, targets, monitors, memberships and assignments. Realm-scoped monitoring
queries expose current distributed state, recent observations and typed history
for ICMP, HTTP/HTTPS, TCP, DNS and TLS. Availability semantics distinguish
configuration delay, missing data, probe failure, target failure, stale agents
and offline agents rather than reducing all failures to a single status.

ICMP history preserves individual RTT samples and packet loss in per-agent
SmokePing-style visualizations. Series are kept separate between agents and are
explicitly broken across missing observations so gaps are not rendered as zero
or fabricated continuity. Selectable time ranges, probe-specific result details,
empty/loading/failure states and frontend behavior tests complete the dashboard
slice. The public `website/` application provides the end-user documentation for
configuring and exercising the V1 workflow locally.

Deliverables:

- target, monitor, agent, group and assignment management interfaces;
- current health and recent execution views;
- SmokePing-style latency-distribution graphs;
- packet-loss and probe-specific detail views;
- cross-agent comparison; and
- accessible empty, loading, failure and missing-data states.

Acceptance criteria:

- A user can complete the V1 configuration workflow without editing files.
- UI writes flow through documented management APIs.
- Graphs preserve distributions and distinguish missing data from zero values.
- Relevant frontend behavior has component/unit coverage in addition to build,
  type and lint checks.

### Stage 10: Alerts and notifications

**Status: Not started**

Objective: provide a small, reliable alerting foundation without attempting a
full incident-management platform.

Deliverables:

- alert rules scoped to realms and monitors;
- pending, firing and resolved state;
- configurable evaluation windows/debounce;
- email and webhook delivery through Celery;
- notification attempt history and retry behavior; and
- audit/security events for alert configuration changes.

Acceptance criteria:

- Alert state survives process restarts.
- Transient single failures do not necessarily fire when a rule requires a
  sustained condition.
- Notification redelivery is idempotent enough to avoid uncontrolled duplicate
  delivery.
- Realm boundaries are enforced for rules, state and notification channels.

### Stage 11: Packaging, deployment and V1 operations

**Status: Not started**

Objective: make the supported self-hosted deployment predictable to install,
operate, back up and upgrade.

Deliverables:

- documented Docker Compose deployment;
- published control-plane and agent images;
- agent binaries for supported platforms;
- documented Linux service installation and ICMP capability setup;
- backup and restore procedures;
- migration and upgrade runbook; and
- health/readiness checks suitable for deployment automation.

Acceptance criteria:

- A clean self-hosted installation can be brought online from documentation.
- Persistent volumes and secrets are explicit.
- Database backups restore into a working instance.
- Upgrade instructions account for database migrations and agent compatibility.

## Post-V1 roadmap

Candidate work after the V1 boundary includes:

- traceroute, MTR and route-history analysis;
- SNMP and broader network-device monitoring;
- bandwidth testing and `iperf3` integration;
- custom executable probes;
- public status pages;
- SAML and enterprise SSO;
- hosted public probe locations;
- official Terraform and Ansible integrations;
- richer notification integrations;
- advanced retention and continuous aggregation policies;
- multi-region BifrostNMS Cloud infrastructure; and
- automated incident correlation or diagnosis.

Post-V1 items should be promoted into delivery stages only when their architecture
and product scope are deliberately accepted.
