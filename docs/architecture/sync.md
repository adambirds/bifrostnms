# Agent observation synchronization

## Purpose

This document defines how durable observations move from agent SQLite storage to
the control plane. It assumes the identities and result schemas from
`measurements.md`, authentication from `agent-protocol.md`, and local durability
from `agent-storage.md`.

The synchronization contract is at-least-once delivery with idempotent server
acceptance. It is not exactly-once transport.

## Invariants

- An observation is immutable after its local commit.
- The same retry uses the same `(scheduled_at, observation_id)` and payload.
- The server acknowledges only durable common and typed result rows.
- The agent deletes only identities explicitly acknowledged as accepted or
  duplicate.
- Transport failure never implies rejection or acceptance.
- One bad observation cannot block all newer observations forever.
- Rejection and data loss remain visible to operators.

## Upload endpoint

```text
POST /api/v1/agent/observations
```

The authenticated agent sends a bounded envelope:

```json
{
  "protocol_version": 1,
  "result_schema_version": 1,
  "agent_config_revision": 42,
  "batch_id": "<uuid>",
  "observations": []
}
```

`batch_id` correlates logs and retries but is not the observation idempotency
key. Rebuilding a batch after partial acknowledgement may use a new batch ID.

The final serialized request must satisfy both the observation-count and byte
limits. The agent selects rows oldest first by `scheduled_at`, then stable UUID,
unless server backpressure directs otherwise.

## Validation and trust

The server derives realm and agent identity from the bearer credential. For each
observation it validates:

- envelope and result schema versions;
- observation identity and timestamp bounds;
- monitor and configuration revision ownership;
- probe type and typed result shape;
- configured packet/result bounds;
- finite numeric values and legal ranges; and
- canonical payload size.

The server does not trust a payload `realm_id` or `agent_id` as authority. If
those fields are included for contract clarity, they must exactly match the
authenticated identity.

The server performs no outbound probe work while validating ingestion.

## Per-observation results

V1 uses explicit per-observation results rather than making one malformed item
prevent acknowledgement of every valid item in a long offline batch.

Example response:

```json
{
  "protocol_version": 1,
  "batch_id": "<uuid>",
  "results": [
    {
      "scheduled_at": "2026-08-16T12:00:00Z",
      "observation_id": "<uuid>",
      "disposition": "accepted"
    },
    {
      "scheduled_at": "2026-08-16T12:01:00Z",
      "observation_id": "<uuid>",
      "disposition": "duplicate"
    },
    {
      "scheduled_at": "2026-08-16T12:02:00Z",
      "observation_id": "<uuid>",
      "disposition": "rejected",
      "code": "unknown_configuration_revision",
      "retryable": true
    }
  ],
  "retry_after_seconds": null
}
```

Allowed dispositions are:

```text
accepted
duplicate
rejected
```

`accepted` and `duplicate` are terminal success dispositions. `rejected` always
contains a stable code and `retryable` flag.

The server returns exactly one result for every supplied identity, in request
order. A missing, repeated or unknown result identity makes the entire response
untrustworthy; the agent performs no cleanup and retries safely.

## Server transaction behavior

Each observation's common and typed rows commit atomically. The implementation
may process a batch in one transaction with savepoints or in bounded subgroups,
but it must not report `accepted` before that observation is durable.

Exact duplicate canonical payloads produce `duplicate`. A matching identity with
different canonical content produces a permanent `idempotency_conflict`, is not
overwritten, and is surfaced as a security/operational event.

Unexpected database failure returns no terminal success for affected rows.

## Retryable rejection

Examples include:

- a configuration revision that has not reached a temporarily lagging server
  component;
- transient ingestion capacity limits;
- a temporarily unavailable database; and
- rate limiting.

The agent retains the row, records the error and schedules another attempt using
server `retry_after_seconds` when supplied.

Retryable rejection counts are bounded and visible. If the same row remains
retryable beyond a configured duration, the agent continues preserving it but
reports a stuck-queue condition rather than silently reclassifying it as
permanent.

## Permanent rejection

Examples include:

- unsupported old protocol/result schema;
- malformed immutable payload;
- timestamp outside the accepted offline/future window;
- monitor belonging to a different agent or realm;
- idempotency conflict; and
- values outside documented hard bounds.

The agent moves the row to local quarantine after a trustworthy permanent
rejection response. It does not repeatedly block the queue and does not silently
delete the evidence.

Authorization failures affecting the whole credential are not converted into
per-row permanent rejection. The uploader stops, preserves the queue and reports
the credential failure for operator action.

## Ordering and head-of-line behavior

Oldest-first upload gives backlog recovery predictable behavior and lets the UI
reason about the remaining gap.

Rows delayed by `next_attempt_at` are skipped temporarily so one retryable
failure does not block every newer row. Permanent failures move to quarantine.
Ordering is therefore best effort across failures, not a guarantee that the
server accepts every observation in strict timestamp order.

Results and graphs must already tolerate late data.

## Backoff

After transport or retryable server failure, the agent uses capped exponential
backoff with full jitter. Initial working values are:

```text
initial delay       1 second
maximum delay       5 minutes
```

Successful contact reduces or resets the failure counter. `429` and explicit
server retry guidance take precedence when they request a longer safe delay.

Heartbeat/config traffic and observation upload have separate bounded backoff
state so a large ingestion backlog does not prevent credential/configuration
diagnostics. All traffic still honors server-wide rate limits.

## Batch sizing

The initial maximum is 500 observations and 1 MiB serialized. The agent builds a
batch incrementally and stops before either limit.

If one legal observation exceeds the batch byte limit, the agent does not loop
forever. It quarantines it with `local_payload_too_large`, reports the condition
and continues. Probe schemas should make this impossible under normal validated
configuration.

The server may advertise lower temporary limits. An agent receiving `413`
reduces the batch size and retries; it does not split one observation.

## Local acknowledgement cleanup

After validating a response, the agent begins one SQLite transaction:

- delete pending rows marked `accepted` or `duplicate`;
- update retry metadata for retryable rejections;
- move permanent rejections to quarantine; and
- update synchronization timestamps/counters.

If this transaction fails or power is lost, all affected rows remain pending and
can be uploaded again. Server idempotency makes that safe.

Acknowledgement cleanup does not depend on `batch_id` alone.

## Configuration revisions and delayed data

The server retains immutable configuration snapshots long enough to validate the
maximum accepted offline backlog plus operational safety margin. Receiving data
from an older still-retained revision is normal after an outage.

A revision older than the retention window is a permanent rejection only when
the server can no longer validate its monitor identity and schema safely. The
retention configuration must prevent this during the documented supported
offline period.

Removing or archiving a monitor stops future scheduling but does not invalidate
legitimate observations executed under a previously acknowledged revision.

## Clock and timestamp validation

The server accepts late event time within the configured offline window. It
rejects timestamps beyond a small documented future tolerance and flags material
clock skew using heartbeat estimates.

Receipt order never rewrites `scheduled_at`. `received_at` is server-generated
for every newly accepted row.

An agent wall-clock correction can make adjacent scheduled timestamps non-
monotonic. Observation UUIDs and durable scheduler state prevent that from
becoming an idempotency collision.

## Server overload

The control plane protects itself with:

- authenticated per-agent and per-realm rate limits;
- request byte and item limits;
- bounded validation work;
- bounded database transactions; and
- explicit retry guidance.

It must prefer rejecting work retryably over accepting a request into volatile
memory and acknowledging before persistence.

Agents naturally apply backpressure through their durable queue. Queue pressure
behavior is defined in `agent-storage.md`.

## Observability

The control plane records bounded metrics for:

- accepted, duplicate and rejected rows;
- ingestion latency from scheduled and finished times;
- batch size and transaction duration;
- per-code rejections;
- agent backlog age/size; and
- idempotency conflicts.

Metrics and logs include realm/agent identifiers only according to operational
access policy. They never include bearer credentials or full probe payloads.

The dashboard should show backlog recovery and quarantined counts without
requiring operators to read agent logs.

## Required validation

- Lost HTTP response after durable server commit.
- Duplicate batch and rebuilt batch with new `batch_id`.
- Mixed accepted, duplicate, retryable and permanent results.
- Missing/repeated identities in a malformed response.
- Common/result atomicity under database failure.
- Oldest-first recovery with one stuck row.
- `413`, `429`, server retry guidance and capped jittered backoff.
- Credential revocation while a large queue is pending.
- Data from an archived monitor under an older acknowledged revision.
- Thirty-day offline backlog and late chunk writes.
- Power loss before and after local acknowledgement cleanup.
- Cross-realm payload and idempotency-conflict handling.
