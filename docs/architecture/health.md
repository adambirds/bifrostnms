# Health and missing-data semantics

## Purpose

BifrostNMS must distinguish target health from the health of the monitoring
system itself. A target failure, a failed local probe engine, an offline agent,
an unacknowledged configuration and a missing observation are different states
with different operator actions.

This document defines current-state derivation, cross-agent aggregation, data
coverage and the foundations required by V1 alerts and dashboards.

## Four independent dimensions

Health is not one boolean. BifrostNMS models four dimensions:

1. **Agent connectivity**: whether the control plane is receiving heartbeats.
2. **Probe execution**: whether an assigned probe produced a trustworthy result.
3. **Target assessment**: whether that result satisfied the monitor's health
   conditions.
4. **Data coverage**: whether expected observations are present and recent.

A UI may summarize these dimensions, but storage, APIs and alert evaluation must
not discard the underlying distinctions.

## Source of truth and projections

Immutable observations and heartbeats are the source evidence. Current health is
a derived projection that may be cached in ordinary PostgreSQL for efficient UI
and alert queries.

A proposed `MonitorAgentState` projection contains:

```text
realm_id
monitor_id
agent_id
effective_assignment
desired_config_revision
acknowledged_config_revision
last_observation_id
last_scheduled_at
last_received_at
execution_status
assessment
availability_state
state_since
updated_at
```

The projection is rebuildable from configuration, acknowledgement, heartbeat and
observation data. It is not a replacement for those records.

State updates compare event time and identity. Accepting an old offline backlog
does not overwrite a newer current-state projection. Historical queries still
include the late observation in its correct time bucket.

If transition history is required for auditing or alerts, store explicit
realm-owned health-state events. Do not reconstruct past transition times from a
mutable current row.

## Agent connectivity

Agent connectivity states are:

```text
never_seen
online
stale
offline
disabled
archived
```

The control plane derives them using server receipt time, not an agent-supplied
`online` value.

Initial working thresholds for a 30-second heartbeat interval are:

```text
online       last heartbeat no more than 60 seconds ago
stale        more than 60 but no more than 90 seconds ago
offline      more than 90 seconds ago
```

The final calculation uses the server-issued heartbeat interval plus configured
grace rather than hard-coding these numbers for every installation. Thresholds
must tolerate jitter and brief request failures without making detection
unreasonably slow.

`disabled` and `archived` are administrative lifecycle states and take precedence
over heartbeat freshness in normal displays. Recent heartbeat receipt from a
disabled or archived agent is still an auditable operational anomaly.

Clock skew affects event-time confidence but does not determine connectivity;
heartbeat receipt uses the server clock.

## Observation execution and assessment

As defined in `measurements.md`, an observation separates:

```text
execution_status = completed | failed
assessment       = healthy | unhealthy | unknown
```

Expected network outcomes are completed observations. An HTTP 500, TCP refusal,
DNS NXDOMAIN when an answer is required, TLS validation failure, ICMP timeout or
failed assertion can all be completed but unhealthy results.

`failed` means the agent could not make a trustworthy target assessment because
of a local permission, invalid configuration, resource limit or internal probe
failure. Its assessment is normally `unknown`.

This distinction permits separate alerts such as:

- “the service is unhealthy from London”; and
- “the London agent cannot execute ICMP because `CAP_NET_RAW` is missing.”

## Expected observations

An observation is expected only when all of these are true:

- the agent, target and monitor are enabled and not archived;
- an enabled direct or agent-group assignment is effective;
- the relevant desired configuration has been acknowledged by the agent;
- the monitor is within its active scheduling policy; and
- the agent has had enough time to execute and upload the scheduled result.

No missing-data judgment is made for configuration the agent has not yet
acknowledged. That condition is `pending_configuration`.

The expected deadline for one scheduled execution is derived from:

```text
scheduled time
+ configured timeout
+ bounded scheduler allowance
+ bounded upload allowance
```

The allowance must be documented and must not grow automatically with an offline
backlog. An agent can be offline while legitimately holding results locally; the
current UI shows the connectivity/coverage problem immediately, while late
history is repaired after synchronization.

## Assignment availability state

For one effective monitor-agent pair, the derived availability state is one of:

```text
pending_configuration
no_data_yet
healthy
unhealthy
probe_error
overdue
agent_stale
agent_offline
disabled
```

### Precedence

Apply these rules in order:

1. A non-effective or administratively disabled assignment is `disabled`.
2. A desired revision not yet acknowledged is `pending_configuration`.
3. A stale/offline agent is `agent_stale` or `agent_offline`.
4. Before the first expected deadline passes, no observation is `no_data_yet`.
5. After an expected deadline passes with no row, state is `overdue`.
6. A recent failed execution is `probe_error`.
7. A recent completed unhealthy result is `unhealthy`.
8. A recent completed healthy result is `healthy`.

This precedence prevents an old healthy observation from hiding a newly offline
agent and prevents configuration rollout from appearing as packet loss.

The API also returns the underlying latest execution/assessment and timestamps,
not only the derived availability state.

## Late and out-of-order observations

Late data repairs historical coverage and aggregates for its event-time bucket.
It changes current state only when it is newer than the projection's latest
event according to the protocol's stable comparison rules.

Receipt time breaks ties for operational diagnostics but does not make an older
scheduled observation current merely because it arrived later.

An observation may arrive after the assignment is removed or monitor archived if
it was executed under an older acknowledged configuration. It remains valid
history but does not reactivate the assignment or current monitor state.

## Monitor aggregation across agents

A monitor summary returns counts for every assignment availability state plus a
derived headline:

```text
healthy
degraded
unhealthy
unknown
disabled
```

The headline rules are:

- `disabled`: there are no effective enabled assignments;
- `unknown`: there are effective assignments but none has a recent trustworthy
  healthy or unhealthy assessment;
- `healthy`: every effective assignment has a recent healthy assessment;
- `unhealthy`: every effective assignment has a recent unhealthy assessment;
- `degraded`: any other mixture, including different health by vantage point or
  a trustworthy assessment mixed with offline/overdue/probe-error states.

This deliberately requires complete agreement before declaring a distributed
monitor wholly healthy or wholly unhealthy. A target unhealthy from Manchester
but healthy from London is `degraded`, which is the important distributed signal.

The summary never hides its denominator. It includes total effective agents,
healthy/unhealthy counts, unavailable counts and coverage percentage.

## Target aggregation across monitors

Targets may have several monitors with different purposes. V1 target summaries
use:

```text
healthy
degraded
unhealthy
unknown
disabled
```

- `disabled`: no enabled monitors have effective assignments;
- `unknown`: no enabled monitor has a trustworthy headline;
- `healthy`: every enabled monitor is healthy;
- `unhealthy`: every enabled monitor is unhealthy;
- `degraded`: any other mixture.

The UI must show monitor breakdowns because an HTTP failure and an ICMP success
are not contradictory: the host may be reachable while the service is broken.

Future product work may allow explicitly critical/noncritical monitors to affect
the target headline differently. V1 does not hide monitor failures behind an
implicit weighting system.

## Data coverage and availability calculations

Coverage and target availability are separate metrics.

For a time window:

```text
coverage = received expected observations / expected observation slots
```

Expected slots are derived from acknowledged configuration history, assignments
and scheduling policy. They are not estimated only from the number of rows that
happened to arrive.

Probe availability is:

```text
healthy completed observations
---------------------------------------------
healthy + unhealthy completed observations
```

`probe_error` and missing observations are reported separately rather than
quietly counted as either target success or target failure. A UI may additionally
offer an operational/SLA calculation that treats missing data as failure, but it
must be named and configured explicitly.

Packet-loss percentages are aggregated from packet totals:

```text
1 - (sum packets_received / sum packets_sent)
```

They are never calculated by averaging observation percentages.

## Configuration and deployment state

Agent configuration state is visible independently:

```text
current
pending
rejected
incompatible
```

An incompatible or rejected configuration does not become a target failure. It
is an operational configuration problem and leaves the last valid snapshot
active as defined in `agent-protocol.md`.

Dashboard summaries should surface pending/rejected/incompatible counts near
health counts so operators do not mistake incomplete rollout for full coverage.

## Alert foundations

V1 alerts evaluate explicit dimensions rather than one generic health boolean.
Initial condition families are:

- target assessment unhealthy;
- latency threshold;
- packet-loss threshold;
- certificate-expiry threshold;
- agent offline;
- observation overdue; and
- probe execution/configuration error.

Alert rules define scope (assignment, monitor or target), threshold, minimum
duration or consecutive count, recovery condition and notification policy.

Alerts do not fire on the first transient state unless configured to do so.
State changes are idempotent, and late observations do not reopen or rewrite a
current incident based solely on old event time.

Cross-agent monitor alerts may distinguish:

- one vantage point unhealthy (`degraded`);
- all vantage points unhealthy (`unhealthy`); and
- monitoring coverage unavailable (`unknown`).

## API response requirements

Health APIs return:

- headline state;
- component counts;
- coverage and its denominator;
- latest relevant event and receipt times;
- agent connectivity state;
- configuration state;
- latest execution status and target assessment; and
- stable machine-readable reason codes.

Clients must not infer missing data from absent optional numeric fields. The API
represents state explicitly and uses `null` for measurements that do not exist.

## Cache and recomputation

Current-state projections may be updated during ingestion and configuration or
heartbeat changes. Periodic reconciliation repairs missed updates and transitions
time-based states such as stale, offline and overdue.

Projection updates are idempotent. The implementation supplies a rebuild command
or job before treating the cache as operationally critical.

The database remains authoritative; Redis may assist live delivery but must not
be the only location of current health state.

## Required validation

- Agent stale/offline transitions use server receipt time.
- Pending configuration does not appear as missing target data.
- First-run grace transitions from `no_data_yet` to `overdue`.
- Latest healthy data cannot hide a newly offline agent.
- Old backlog repairs history without replacing newer current state.
- Mixed vantage-point results produce `degraded` with accurate counts.
- All-vantage healthy/unhealthy rules require complete effective coverage.
- Disabled/archived resources stop generating expected slots.
- Group membership changes update effective assignment state.
- Coverage uses acknowledged configuration history.
- Probe availability excludes and separately reports missing/probe-error rows.
- Packet-loss aggregation uses sent/received totals.
- Projection rebuild produces the same current states.
- Realm isolation applies to current state, transitions and alert evaluation.
