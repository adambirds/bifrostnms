# Agent local storage

## Purpose

The BifrostNMS agent uses SQLite so probe scheduling and observation capture
continue when the control plane or network is unavailable. SQLite is durable
agent state, not merely a disposable cache.

This document defines ownership, schema responsibilities, transactions,
migrations, limits and failure behavior. The wire protocol is defined in
`agent-protocol.md` and synchronization in `sync.md`.

## Storage location and permissions

The default Linux location is:

```text
/var/lib/bifrostnms-agent/agent.db
```

The parent directory and database files are accessible only to the dedicated
agent service account. Packaging creates the directory with restrictive
ownership and permissions before the process starts.

The path is configurable for containers and non-Linux platforms. Containers
must mount it on persistent storage; running with an ephemeral database should
require an explicit development/testing option and a prominent warning.

SQLite stores the active agent credential because the agent must authenticate
without operator interaction. Encrypting it with a key stored beside the
database would not protect against host compromise. V1 instead relies on host
filesystem permissions, supports credential revocation and rotation, and never
logs the secret. Platform keystore integration may be added later.

## SQLite configuration

The initial database settings are:

```text
journal_mode = WAL
foreign_keys = ON
busy_timeout = bounded nonzero value
synchronous = FULL for identity, configuration and observation commits
```

Durability settings must be verified on every connection rather than assumed
from one setup call. Performance testing may justify a different documented
setting, but pending observations must not be knowingly acknowledged to the
scheduler before their durable commit.

The agent should use one controlled write path and a bounded connection pool.
Probe workers produce results through application channels; they do not each
open uncoordinated write transactions.

## Schema migrations

The database contains a schema-version table and ordered migrations embedded in
the Go binary.

On startup the agent:

1. opens the database;
2. checks integrity and the schema version;
3. applies required migrations transactionally;
4. refuses to start normal scheduling if a migration fails; and
5. emits a clear local operational error without exposing secrets.

An older binary must not open a database with a newer unsupported schema. Agent
upgrade and rollback documentation must state which schema versions are
compatible. Destructive migrations require an explicit backup/upgrade strategy.

## Proposed tables

### Agent identity

One row stores:

```text
agent_id
realm_id
control_plane_url
enrolled_at
```

Identity is immutable after enrolment. Pointing an enrolled database at a
different control plane or realm requires an explicit reset/re-enrol operation;
it must not happen from an environment-variable typo.

### Credentials

Credential rows store:

```text
credential_id
secret
created_at
activated_at
retire_after
```

The schema supports an active and pending credential during rotation. The agent
does not delete the old credential until the server confirms the new credential
and the rotation protocol permits retirement.

### Configuration snapshots

Each downloaded snapshot stores:

```text
revision
content_hash
schema_version
canonical_payload
downloaded_at
validated_at
activated_at
rejection_code
rejection_details
```

Only one snapshot is active. Download, validation metadata and activation occur
in a transaction that cannot leave two active snapshots.

The agent retains the active snapshot and at least one previous valid snapshot
for diagnosis and controlled rollback. Rejected snapshots may retain bounded
metadata but not an unlimited series of large payloads.

### Pending observations

Each durable observation stores:

```text
scheduled_at
observation_id
monitor_id
monitor_revision
agent_config_revision
probe_type
canonical_payload
payload_size_bytes
created_at
attempt_count
next_attempt_at
last_attempt_at
last_error_code
```

`(scheduled_at, observation_id)` is unique and matches server idempotency.
Observation payloads are immutable after insertion. Retry metadata changes, but
the canonical observation does not.

The scheduler considers a probe execution recorded only after this row commits.
It never treats an in-memory upload queue as durable storage.

### Rejected observations

Permanently rejected observations move to a bounded local quarantine table with:

```text
observation identity
canonical payload
rejection code
bounded rejection details
rejected at
```

They are not retried indefinitely and are not silently deleted. Agent status and
local diagnostics expose their count. Retention limits prevent malformed data
from filling the disk forever.

### Synchronization state

Synchronization metadata includes:

```text
last_successful_contact_at
last_successful_upload_at
consecutive_failure_count
server_backoff_until
oldest_pending_at
```

Derived queue counts and bytes should be queried or maintained transactionally;
they must not drift from the actual pending rows.

### Operational events

A small bounded event table may record durable local conditions such as queue
pressure, clock changes, database-integrity failures and configuration
rejections. It is not a replacement for structured logs and must have explicit
retention.

## Observation transaction

One probe execution is persisted atomically:

```text
begin transaction
  insert immutable pending observation
  update bounded scheduler/run metadata if required
commit
```

Only after commit may the scheduler report the run as durably captured. Upload
can start immediately afterward but is not part of the probe transaction.

If persistence fails, the agent records an operational failure and applies queue
pressure behavior. It must not claim that the observation was synchronized or
discard it from memory without reporting data loss.

## Configuration transaction

Configuration activation is similarly atomic:

```text
begin transaction
  insert validated snapshot
  clear previous active marker
  mark new snapshot active
commit
reconcile scheduler
acknowledge server
```

If scheduler reconciliation fails after commit, the agent stops affected
scheduling, reports the failure and retains the previous valid snapshot for
diagnosis. The implementation must define whether it can transactionally revert
activation before acknowledging; it must never acknowledge configuration it
cannot run.

## Queue limits and backpressure

Offline operation cannot imply unlimited disk usage. The agent has configurable
limits for:

- pending observation count;
- pending payload bytes;
- rejected/quarantined payload bytes; and
- maximum observation age.

Initial V1 defaults are one million pending observations and 1 GiB of pending
payload, with warning thresholds before the hard limit. Installation packages
may choose lower documented defaults for constrained systems.

At the hard limit the default policy is **pause new probe execution** and keep
retrying synchronization. The agent reports a critical local condition and, when
possible, includes it in heartbeat state. It does not silently delete the oldest
unsynchronized observations.

A future operator-selected lossy policy may discard according to explicit rules,
but it must record counts and time ranges of lost observations so gaps remain
explainable.

The configured maximum observation age must not exceed the server's accepted
offline window unless the operator explicitly accepts that old rows can be
quarantined rather than ingested.

## Cleanup

Pending rows are deleted only after the server explicitly acknowledges those
exact observation identities as accepted or already accepted.

Deletion occurs in a local transaction after the response is fully parsed and
validated. Losing power before cleanup simply causes a safe duplicate upload.

Vacuum/checkpoint behavior must be scheduled so cleanup actually releases or
reuses space without blocking probe writes for an unbounded period. The agent
reports database file size separately from logical pending bytes.

## Concurrency and shutdown

Configuration activation, scheduling, observation writes, uploads and cleanup
share explicit ownership rules.

On graceful shutdown the agent:

1. stops accepting new scheduled executions;
2. cancels in-flight probes with a deadline;
3. persists any complete results;
4. stops new upload batches;
5. completes or rolls back active SQLite transactions; and
6. closes the database.

Shutdown does not wait indefinitely for network synchronization. Durable pending
rows remain for the next start.

## Corruption and recovery

Startup performs lightweight integrity checks appropriate for normal operation.
The `doctor` command should provide a deeper offline integrity check and bounded
diagnostic output.

If SQLite reports corruption, the agent stops scheduling rather than replacing
the database and losing identity/configuration/observations silently. Recovery
documentation must preserve the damaged file for operator inspection and offer
explicit repair, restore or re-enrol paths.

Re-enrolment into a new database does not pretend that pending rows in an old
database were uploaded.

## Backup and portability

Agents are designed to recover configuration from the control plane, but pending
observations exist only locally until acknowledged. Filesystem snapshots must
respect SQLite WAL consistency. A future backup command should use SQLite's
supported backup mechanism rather than copying only `agent.db` while it is live.

Database contents are not a stable public API. Operators use documented agent
commands for status, diagnostics and reset rather than editing tables manually.

## Required validation

- Power loss after observation commit and before upload cleanup.
- Restart with a pending queue and no control-plane access.
- Atomic configuration activation and last-known-good preservation.
- Unsupported newer database schema.
- Transactional migration failure.
- Credential rotation interruption.
- Queue warning and hard-limit behavior.
- No silent deletion under disk pressure.
- Concurrent scheduling, upload and acknowledgement cleanup.
- Graceful and forced shutdown.
- Corruption detection and explicit recovery behavior.
