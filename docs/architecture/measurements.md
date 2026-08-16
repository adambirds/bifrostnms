# Observations and measurements

## Purpose

This document defines how BifrostNMS stores and queries monitoring results. It
builds on the realm, agent, target and monitor identities in `data-model.md` and
must be settled before implementing ingestion or TimescaleDB migrations.

The design must support all of these workloads without treating one as an
afterthought:

- idempotent batches arriving from agents after network outages;
- current health and recent-failure queries across probe types;
- SmokePing-style latency-distribution graphs;
- probe-specific diagnostic views;
- cross-agent comparison for one monitor;
- retention and downsampling over long-running installations; and
- efficient realm isolation.

## Decision summary

BifrostNMS uses:

1. one common `observations` TimescaleDB hypertable;
2. one typed result hypertable for each V1 probe family;
3. individual ICMP RTT values stored as a bounded array on the ICMP result row;
4. continuous aggregates for common operational summaries where ordinary SQL
   aggregates preserve the required meaning;
5. application-owned rollups where latency distributions cannot be preserved by
   a simple average; and
6. configurable retention policies that never drop source data before required
   rollups are durable.

This rejects three tempting alternatives:

- one wide table would contain many meaningless nullable columns;
- JSON-only results would weaken validation and make core graph queries harder
  to index and evolve; and
- one generic row per named metric would multiply ingestion volume and lose the
  natural identity of one probe execution.

## Terminology

An **observation** is one scheduled execution of one monitor by one agent.

A **result** is the typed, probe-specific data produced by that observation.

A **raw sample** is an individual value inside a result, such as one successful
ICMP round-trip time.

A **rollup** summarizes source observations over a time bucket while preserving
the semantics required by a particular visualization or alert.

Missing data is the absence of an expected observation. It is not an observation
whose numeric values happen to be zero.

## Common observation hypertable

The `observations` hypertable provides cross-probe identity, timing, execution
state and health assessment.

Proposed columns:

```text
scheduled_at           TIMESTAMPTZ, required
observation_id         UUID, required
realm_id               UUID, required
agent_id               UUID, required
monitor_id             UUID, required
probe_type              constrained text, required
monitor_revision        BIGINT, required
agent_config_revision   BIGINT, required
started_at              TIMESTAMPTZ, required
finished_at             TIMESTAMPTZ, required
received_at             TIMESTAMPTZ, required, server-generated
execution_status        constrained text, required
assessment              constrained text, required
error_category          nullable constrained text
error_code              nullable bounded text
error_message           nullable bounded text
agent_clock_offset_ms   nullable integer
```

`scheduled_at` is the hypertable time dimension. It represents the intended
execution time in the agent's schedule and is the time used on monitoring
graphs. `received_at` records when the control plane accepted the row and is
used for ingestion diagnostics and backlog visibility.

The server must not overwrite agent event times with receipt time merely because
a batch arrived late. It must validate impossible timestamps and record known
clock-offset information so the UI can warn when an agent's clock is unreliable.

The initial chunk interval should be seven days. This is a starting operational
default, not a permanent constant: implementation must expose it in one reviewed
migration and measure chunk sizes under realistic ingestion before changing it.

V1 partitions by time only. A realm/agent space dimension is not justified until
write volume and storage topology demonstrate a benefit. Adding dimensions
multiplies chunks and also constrains unique indexes.

## Identity and idempotency

The agent generates `observation_id` and persists the complete observation in
SQLite before attempting upload. Retries reuse the same ID and immutable
`scheduled_at`.

TimescaleDB unique indexes must include every partitioning column. Therefore the
hypertable idempotency key is:

```text
UNIQUE (scheduled_at, observation_id)
```

The ingestion API treats that pair as immutable:

- a new pair is inserted;
- an existing pair with the same canonical payload is acknowledged as already
  accepted; and
- an existing pair with different content is rejected as an idempotency
  conflict and recorded for operational investigation.

An honest agent cannot create the same durable observation with a different
`scheduled_at`; changing it would be a different payload and a protocol error.
Agent authentication, batch limits and conflict monitoring protect against
deliberately manufactured duplicates across time chunks.

If production evidence shows that globally enforcing `observation_id` alone is
necessary, add a compact relational ingestion ledger rather than pretending a
time-partitioned unique index provides that guarantee.

## Execution and health semantics

`execution_status` describes whether the probe engine completed its work:

```text
completed
failed
```

`assessment` describes the target result:

```text
healthy
unhealthy
unknown
```

These dimensions are separate. Examples:

| Situation                                       | Execution   | Assessment   |
| ----------------------------------------------- | ----------- | ------------ |
| HTTP request returns expected 200               | `completed` | `healthy`    |
| HTTP request returns unexpected 500             | `completed` | `unhealthy`  |
| TCP connection is refused                       | `completed` | `unhealthy`  |
| Probe lacks required socket capability          | `failed`    | `unknown`    |
| Agent process crashes before recording a result | no row      | missing data |

Expected network outcomes should normally be completed observations, even when
they are unhealthy. `failed` is reserved for cases where the probe could not
produce a trustworthy assessment because of local capability, configuration or
internal execution problems.

Initial `error_category` values are:

```text
timeout
resolution
connection
tls
protocol
assertion
permission
invalid_configuration
resource_limit
internal
```

The protocol specification may refine this taxonomy, but it must keep stable
machine-readable categories separate from bounded human-readable messages.
Agents must never upload secrets, full response bodies or uncontrolled error
strings.

## Common indexes

The initial observation indexes should support the known V1 query shapes:

```text
UNIQUE (scheduled_at, observation_id)
(realm_id, monitor_id, agent_id, scheduled_at DESC)
(realm_id, agent_id, scheduled_at DESC)
(realm_id, assessment, scheduled_at DESC)
(realm_id, received_at DESC)
```

The migration must validate these against representative `EXPLAIN` plans before
Stage 3 is complete. Indexes are not added speculatively for every column.

The leading `realm_id` makes tenancy explicit and makes ordinary graph and
overview queries naturally realm-scoped. `received_at` supports backlog and
ingestion-lag diagnostics even though chunks are partitioned by `scheduled_at`.

## Typed probe result hypertables

Each V1 probe family has one typed hypertable keyed by the same observation
identity:

```text
scheduled_at
observation_id
realm_id
agent_id
monitor_id
```

The duplicated realm/agent/monitor columns are intentional. They let graph
queries stay realm-scoped and chunk-local without joining the common table merely
to discover tenancy. Ingestion derives and verifies these values from the
authenticated agent and accepted monitor configuration.

The common and typed rows are inserted in one PostgreSQL transaction. An
observation is never acknowledged until both are durable. An observation with no
typed row is valid only when its execution failed before a probe-specific result
could be produced.

The result hypertables use the same time chunk interval as `observations` unless
measured workloads justify a probe-specific value.

### ICMP results

Proposed columns:

```text
packets_sent            integer
packets_received        integer
packet_loss_percent     double precision
min_rtt_ms              nullable double precision
avg_rtt_ms              nullable double precision
median_rtt_ms           nullable double precision
max_rtt_ms              nullable double precision
p95_rtt_ms              nullable double precision
jitter_ms               nullable double precision
rtt_samples_ms          double precision[]
```

`rtt_samples_ms` contains one value for each successful reply in packet sequence
order. Lost packets are represented by the sent/received counts rather than NaN
or sentinel values in the array.

The monitor schema places a strict upper bound on packet count, so the array is
bounded. Summary columns are generated by the agent and verified or recomputed
by the server according to the protocol contract.

The exact jitter formula and percentile interpolation method must be specified
in the probe contract. They cannot vary by agent version without being reflected
in protocol/result schema versions.

### HTTP/HTTPS results

Proposed columns:

```text
method                  bounded text
scheme                  constrained text
status_code             nullable integer
redirect_count          integer
response_size_bytes     nullable bigint
dns_ms                  nullable double precision
connect_ms              nullable double precision
tls_ms                  nullable double precision
ttfb_ms                 nullable double precision
total_ms                nullable double precision
assertions_total        integer
assertions_failed       integer
final_url_redacted      nullable bounded text
```

HTTPS uses this table with `scheme = 'https'`. Detailed assertion outcomes may
use a bounded JSON object when their schema is typed by the protocol; arbitrary
response bodies and sensitive URL components must not be stored.

### TCP results

Proposed columns:

```text
port                    integer
address_used            inet
connect_ms              nullable double precision
```

Connection refusal and timeout remain distinguishable through the common
assessment and error category.

### DNS results

Proposed columns:

```text
resolver_address        inet
query_name              bounded text
query_type              constrained text
response_code           nullable constrained text
response_ms             nullable double precision
answer_count            integer
answers                 typed bounded JSON array
truncated               boolean
authoritative           boolean
assertions_total        integer
assertions_failed       integer
```

DNS answers are heterogeneous across record types, so a versioned bounded JSON
array is appropriate here. Core filter/graph values remain typed columns.

### TLS certificate results

Proposed columns:

```text
port                    integer
server_name             bounded text
protocol_version        nullable bounded text
cipher_suite            nullable bounded text
handshake_ms            nullable double precision
certificate_present     boolean
hostname_valid          nullable boolean
chain_valid             nullable boolean
not_before              nullable timestamptz
not_after               nullable timestamptz
days_remaining          nullable double precision
subject_name            nullable bounded text
issuer_name             nullable bounded text
serial_number           nullable bounded text
fingerprint_sha256      nullable bounded text
```

Full certificate chains are not stored in every observation. Stable metadata
needed for change detection may later use a separate deduplicated certificate
entity if product requirements justify it.

## Foreign keys and historical identity

Agent, target and monitor records are archived rather than routinely deleted.
Stage 3 should use foreign keys from ordinary configuration tables where they
protect domain integrity.

For high-volume hypertables, migrations must benchmark the write and retention
cost of foreign keys to ordinary tables before enabling them. Realm-scoped
ingestion validation is mandatory regardless. Time-series retention must not be
blocked by a cascade or mutable-domain deletion.

Observations reference immutable monitor and agent UUIDs plus configuration
revisions. Agent configuration snapshots or equivalent retained revision data
must preserve the target address and probe configuration applied at execution
time. Historical rows do not duplicate mutable display names; the UI may show
the current archived entity name and provide the applied configuration details
for historical interpretation.

## Batch ingestion

The agent uploads a bounded batch containing common observation fields and one
typed result per successfully executed probe.

The server performs this sequence:

1. Authenticate the agent and derive its realm.
2. Enforce request-size, observation-count and timestamp bounds.
3. Validate the protocol/result schema version.
4. Validate monitor, agent and configuration-revision ownership.
5. Canonicalize and validate every observation before writing any row.
6. Insert common and typed rows in one transaction using bulk operations.
7. Treat exact duplicate keys as already accepted.
8. Return explicit accepted, duplicate and rejected identities.

A partially valid batch is not silently acknowledged. The protocol design must
choose between atomic rejection and explicit per-item results; in either case an
agent deletes a local row only after that exact observation is acknowledged.

Row-at-a-time Tortoise `create()` calls are not suitable for ingestion. Stage 3
may use parameterized PostgreSQL bulk SQL behind a typed repository boundary.

## Late data and clock behavior

Offline agents may upload observations into older chunks. Retention and
columnstore policies must leave a documented writable window at least as long as
the maximum supported offline backlog.

V1 should support at least 30 days of offline backlog. An installation may
configure a longer local queue and server acceptance window, but the two values
must be validated together. Data older than the server acceptance window is
rejected explicitly rather than acknowledged and discarded.

The agent records its local wall-clock event times and monotonic durations. The
server estimates wall-clock offset during trusted communication. It rejects
timestamps unreasonably far in the future, records material skew and surfaces
that condition separately from target health.

Changing an agent's wall clock must not produce negative durations because probe
durations use a monotonic clock.

## Missing data and derived state

The database stores observations, not fabricated failure rows for executions
that never arrived.

Missing data is derived from:

- enabled effective assignment;
- acknowledged agent configuration revision;
- expected monitor interval;
- agent heartbeat recency;
- accepted observations; and
- a documented grace period.

The UI and alerting layer must distinguish at least:

```text
healthy observation
unhealthy observation
probe execution failure
agent offline
observation overdue while agent appears online
configuration not yet acknowledged
no data yet
```

These states must not be collapsed into a zero value or one generic `down`
boolean. The precise state machine belongs to the health-design document.

## Query and graph behavior

V1 graph APIs query by explicit realm, monitor, agent set and bounded time range.
The server selects a bucket width based on the requested range and maximum point
budget; clients do not request unbounded raw history.

For ranges within raw retention, ICMP smoke graphs use `rtt_samples_ms` so the
distribution is genuine rather than inferred from an average. Packet loss uses
the sum of sent and received counts, not the average of per-observation
percentages.

Cross-agent comparisons use aligned time buckets but preserve missing buckets.
Gap filling may generate empty buckets for presentation; it must not carry a
latency or health value forward as if a probe ran.

HTTP timing, TCP connection, DNS response and TLS handshake/certificate graphs
read their typed result columns. Common overview queries read `observations`
without unioning every result table.

## Rollups and continuous aggregates

Continuous aggregates are appropriate for summaries expressible with stable SQL
aggregates, including:

- observation counts by execution/assessment state;
- packet sent/received totals and packet loss;
- minimum, maximum and average durations; and
- HTTP status classes or other bounded categorical counts.

An average of averages is not used. Rollups retain counts and sums needed to
derive weighted values correctly.

Smoke distributions require more care. Averages, minimum and maximum values do
not reproduce SmokePing's visual meaning. V1 raw-range graphs therefore use the
bounded RTT arrays directly. Before raw ICMP data is dropped, an application-
owned rollup job must store a mergeable distribution representation for longer
ranges. The chosen representation and bucket boundaries require representative
data tests before implementation; fixed logarithmic histograms are the default
candidate.

Do not make TimescaleDB Toolkit a silent mandatory dependency merely to gain a
percentile aggregate. If Toolkit is adopted, pin and document it as part of the
supported database platform and retain an export/migration path for stored
rollup data.

Continuous aggregates refresh recent windows repeatedly to incorporate late
data. Their policies must be coordinated with source retention so refreshes do
not remove aggregate buckets after the underlying raw chunks have already been
dropped.

## Retention and columnstore policy

Retention is configurable because a home installation, a large self-hosted
deployment and BifrostNMS Cloud have different storage budgets. The initial
recommended defaults are:

```text
Raw common and typed observations     90 days
Fine-grained rollups                   2 years
Hourly operational rollups            5 years
```

The 90-day raw window exceeds the minimum 30-day offline backlog. Configuration
must reject a raw-retention window shorter than the accepted offline window plus
the required rollup refresh safety margin.

TimescaleDB retention policies drop complete expired chunks rather than deleting
rows individually. Older finalized chunks should move to TimescaleDB's supported
columnstore/compression mechanism after the late-write window, subject to
version-specific validation in the implementation migration.

No retention policy is added until the required rollup exists and an integration
test proves that long-range graph data survives raw-chunk removal.

Realm deletion is separate from age-based retention and follows the resumable,
auditable tenancy workflow. Shared time chunks mean realm deletion cannot assume
that dropping a chunk affects only one realm.

## TimescaleDB deployment requirement

The current development and CI Compose services use plain `postgres:17-alpine`.
That is incompatible with the settled architecture and must change before Stage
3 migrations introduce hypertables.

Implementation must:

- select and pin a supported self-hosted TimescaleDB image compatible with the
  project's PostgreSQL version;
- enable the extension through a reviewed migration/bootstrap step;
- run migration and integration tests against TimescaleDB in CI;
- document backup, restore and upgrade compatibility; and
- avoid floating `latest` database tags.

Local development, CI and supported production Compose must exercise the same
TimescaleDB major compatibility line.

## Migration ownership

Tortoise's migration system remains the source of migration history. A reviewed
migration may contain explicit SQL for extension creation, hypertables, indexes,
continuous aggregates and policies that Tortoise cannot express directly.

Do not use `generate_schemas()` or startup-time table creation for TimescaleDB
objects. Migrations must be reversible where the underlying operation safely
supports reversal and must clearly document irreversible data-loss operations.

## Validation required before Stage 3 completion

- Bulk ingestion is tested with duplicates and conflicting replays.
- Cross-realm and cross-agent payload references are rejected.
- Common and typed rows commit atomically.
- Thirty-day late data is accepted within the configured window.
- Future and materially skewed timestamps are handled explicitly.
- Representative V1 graph queries have reviewed `EXPLAIN` plans.
- Smoke graphs use real or preserved distribution data.
- Packet-loss rollups use packet totals rather than averaged percentages.
- Retention tests prove required rollups survive raw-chunk removal.
- Migration tests run on the pinned TimescaleDB image.

## Official TimescaleDB references

Implementation should re-check the documentation for the pinned version rather
than copying commands blindly from this design:

- [Hypertable creation](https://docs.timescale.com/api/latest/hypertable/create_hypertable/)
- [Continuous aggregates](https://docs.timescale.com/use-timescale/latest/continuous-aggregates/about-continuous-aggregates/)
- [Retention policies](https://docs.timescale.com/use-timescale/latest/data-retention/create-a-retention-policy/)
- [Unique indexes on hypertables](https://docs.timescale.com/use-timescale/latest/hypertables/hypertables-and-unique-indexes/)
