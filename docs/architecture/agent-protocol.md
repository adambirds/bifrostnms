# Agent protocol

## Purpose

This document defines the V1 control-plane protocol for agent enrolment,
authentication, heartbeat, capability negotiation and desired configuration.
Observation synchronization is defined in `sync.md`; durable local behavior is
defined in `agent-storage.md`.

The protocol is intentionally direct HTTPS/JSON. Agents do not require Celery,
Redis, a message broker or an inbound connection from the control plane.

## Design principles

- Agents initiate every connection.
- The control plane distributes desired state; agents schedule work locally.
- Every payload and configuration schema is explicitly versioned.
- Credentials can be issued, rotated and revoked without replacing agent
  identity.
- Configuration is acknowledged only after durable local activation.
- Mixed agent versions fail visibly rather than silently omitting work.
- Protocol operations are suitable for interactive setup and future unattended
  Ansible deployment.

## Transport

Production agent communication requires HTTPS with certificate verification.
Plain HTTP is permitted only for an explicitly configured local development
environment.

The V1 endpoints live below:

```text
/api/v1/agent/
```

This URL version identifies the HTTP API generation. Request and response
envelopes also carry a protocol version so incompatible wire changes do not
depend only on URL routing.

Agents send a bounded user agent containing the product and semantic version:

```text
BifrostNMS-Agent/0.1.0
```

Secrets must never appear in URLs, query strings, user-agent values, error
messages or logs.

## Agent lifecycle

```text
Administrator creates Agent
          |
          +-- issues one-time enrolment token
                          |
                          v
Agent exchanges token over HTTPS
          |
          +-- receives agent identity and credential once
                          |
                          v
Agent stores identity/credential durably
          |
          +-- heartbeat and capability report
          +-- desired configuration poll
          +-- observation batch upload
```

Creating the `Agent` resource separately from enrolment gives Terraform and the
UI one stable lifecycle. Enrolment does not silently create an unowned agent in
an arbitrary realm.

## Enrolment token

An authorized realm administrator requests a token for one existing agent. The
token is:

- cryptographically random with at least 256 bits of entropy;
- scoped to exactly one realm and agent;
- stored only as a hash on the server;
- single use;
- short lived, with a default lifetime of 15 minutes;
- revocable before use; and
- returned only in the creation response.

Creating a replacement token invalidates any unused previous token for that
agent unless the administrator explicitly requests a separately named concurrent
enrolment. V1 normally permits one active enrolment token per agent.

The future Terraform provider treats the raw token as a sensitive write-only
value. An Ansible workflow can create or request the token, deliver it to the
host, complete enrolment and discard it. A normal read API can report token
metadata but never recover its value.

## Enrolment exchange

The unauthenticated enrolment endpoint accepts the one-time token in the request
body over HTTPS:

```text
POST /api/v1/agent/enrol
```

Example request shape:

```json
{
  "protocol_version": 1,
  "enrolment_token": "<secret>",
  "agent_version": "0.1.0",
  "platform": "linux",
  "architecture": "amd64",
  "hostname": "probe-london-01",
  "capabilities": {}
}
```

The server validates and consumes the token atomically. A successful response
contains:

```json
{
  "protocol_version": 1,
  "agent_id": "<uuid>",
  "realm_id": "<uuid>",
  "credential": "<returned-once secret>",
  "credential_id": "<uuid>",
  "server_time": "2026-08-16T12:00:00Z",
  "heartbeat_interval_seconds": 30,
  "config_poll_interval_seconds": 30
}
```

If the response is lost after the server consumes the token, the raw credential
cannot be recovered. The administrator revokes the unconfirmed credential and
issues a new enrolment token. The UI and API should make this recovery explicit.

An already enrolled agent does not use enrolment again for ordinary restarts or
upgrades.

## Agent credential

V1 uses a random opaque bearer credential. It is practical for unattended
deployment, straightforward to revoke and does not require operating a private
certificate authority in the first release.

The serialized credential contains a non-secret credential identifier and a
256-bit random secret. The identifier permits indexed lookup; the server stores
only a cryptographic hash of the secret and compares it in constant time.

Authenticated requests use:

```text
Authorization: Bearer <agent credential>
```

The server derives the trusted `agent_id` and `realm_id` from the credential. It
never trusts those fields merely because they appear in an agent payload.

Credentials support:

- a human-readable name;
- creation and optional expiry times;
- last-used metadata;
- explicit revocation; and
- rotation with a bounded overlap window.

Rotation issues a new credential once, stores it durably on the agent and then
revokes the old credential after successful confirmation. An interrupted
rotation must leave at least one usable credential. V1 does not automatically
rotate credentials until that recovery flow has integration tests.

Mutual TLS may be added later for deployments that require it, but it must layer
onto agent identity rather than replace realm and credential lifecycle models.

## Protocol version negotiation

Every agent request sends:

```json
{
  "protocol_version": 1
}
```

The server publishes its supported range in authenticated responses:

```json
{
  "minimum_protocol_version": 1,
  "maximum_protocol_version": 1
}
```

If there is no overlap, the server returns a stable incompatible-version error
and does not deliver configuration or accept observations. The agent keeps its
last valid configuration running when safe and reports the incompatibility
locally.

Additive optional fields do not require a new protocol generation when older
agents can safely ignore them. Changing meaning, removing required data or
changing acknowledgement behavior does.

## Capabilities

Capabilities describe what this concrete agent can execute, not merely what its
software version theoretically implements.

Example shape:

```json
{
  "probes": {
    "icmp": { "schema_versions": [1], "available": true },
    "http": { "schema_versions": [1], "available": true },
    "tcp": { "schema_versions": [1], "available": true },
    "dns": { "schema_versions": [1], "available": true },
    "tls": { "schema_versions": [1], "available": true }
  },
  "runtime": {
    "raw_socket": true,
    "ipv4": true,
    "ipv6": true
  },
  "external_tools": {}
}
```

Capability keys and probe schema versions are defined by the protocol contract.
Unknown keys are preserved or ignored according to schema rules; they are not
treated as authorization.

The server must not silently omit an assigned monitor that an agent cannot run.
It marks the assignment/configuration incompatibility visibly and withholds
activation of an invalid desired snapshot until the conflict is resolved.

## Heartbeat

```text
POST /api/v1/agent/heartbeat
```

The heartbeat reports:

- protocol and agent software versions;
- platform, architecture and hostname;
- current capabilities;
- active and desired configuration revisions;
- local queue depth and bytes;
- oldest pending observation time;
- local database health;
- probe scheduler state;
- current agent wall-clock time; and
- bounded operational warnings.

The response supplies server time, supported protocol range, polling intervals
and whether newer desired configuration exists.

The nominal V1 heartbeat interval is 30 seconds with jitter. Online/offline state
is derived rather than written by the agent. The health-state design will define
the final grace period; 90 seconds is the initial working threshold.

Heartbeat metadata must remain bounded. It is not a general log-upload endpoint.

## Desired configuration

```text
GET /api/v1/agent/config
```

The agent sends its active revision using a request header or query parameter
defined by the final OpenAPI contract. The server returns `304 Not Modified`
when that revision and content hash are current.

A configuration response includes:

```json
{
  "protocol_version": 1,
  "configuration_schema_version": 1,
  "agent_id": "<uuid>",
  "realm_id": "<uuid>",
  "revision": 42,
  "content_hash": "sha256:<hex>",
  "generated_at": "2026-08-16T12:00:00Z",
  "monitors": []
}
```

Each monitor entry contains all agent-visible behavior needed to schedule the
probe without further control-plane calls:

- monitor and target UUIDs;
- monitor revision;
- target address;
- probe type and probe schema version;
- interval, timeout and scheduling policy; and
- strictly typed probe-specific configuration.

The payload is canonicalized before hashing. Ordering of monitors and map keys is
deterministic so semantically identical configuration produces the same hash.

The server stores every issued immutable configuration snapshot, its revision,
hash and generation metadata. This permits historical observations to identify
the exact address and probe behavior applied at execution time.

Revisions are monotonic per agent. They may contain gaps after failed generation
or concurrent changes; agents compare values for equality/newness and never
assume every intermediate revision will be delivered.

## Configuration activation and acknowledgement

The agent performs this sequence:

1. Download into memory.
2. Validate envelope, identity, schema versions, hash and every monitor.
3. Persist the complete snapshot to SQLite in one transaction.
4. Atomically mark the snapshot active.
5. Reconcile the local scheduler.
6. Acknowledge the revision to the server.

```text
POST /api/v1/agent/config/acknowledge
```

The acknowledgement contains the revision, hash and activation time. It is
idempotent. Acknowledging a revision never seen by the server is rejected.

If any monitor is invalid or unsupported, the entire snapshot is rejected and
the last valid snapshot remains active. The agent sends a bounded rejection
report identifying stable monitor IDs and machine-readable reasons. Partial
activation would make the server's desired revision misleading and is not
allowed in V1.

Removing an assignment appears as absence from a newer complete snapshot. The
agent stops future scheduling after activation but retains already queued
observations.

## Server-side state

The control plane retains:

- desired revision and hash;
- latest acknowledged revision, hash and time;
- immutable issued snapshots;
- latest heartbeat and capabilities;
- credential lifecycle metadata; and
- bounded configuration rejection details.

Desired configuration generation is deterministic and triggered by relevant
monitor, target, assignment, group or membership changes. Concurrent changes are
serialized per affected agent so two snapshots cannot receive the same revision.

## Error responses

Errors use a stable envelope such as:

```json
{
  "error": {
    "code": "incompatible_protocol",
    "message": "Agent protocol version is not supported.",
    "retryable": false,
    "details": {}
  }
}
```

`code` and `retryable` are protocol fields. Human-readable messages are not used
for program flow. Details are bounded, typed by error code and must not expose
other realms or secrets.

Expected status classes are:

- `400` malformed or semantically invalid request;
- `401` missing or invalid credential;
- `403` valid credential not permitted for the operation;
- `409` revision, idempotency or lifecycle conflict;
- `413` request or batch too large;
- `422` supported envelope with invalid typed content;
- `429` rate limited, with retry guidance; and
- `5xx` retryable server failure unless the error code states otherwise.

## Rate and size limits

Limits are returned in server policy/configuration rather than compiled only
into the agent. Initial V1 defaults are:

```text
Heartbeat request                 64 KiB
Configuration response             2 MiB
Observation upload                 1 MiB
Observations per batch               500
```

These are starting safety limits and require load testing. Agents must split
batches without splitting one observation and must handle `413` without dropping
data.

## Audit and logging

The server audits enrolment-token creation/revocation/use, credential
creation/rotation/revocation and agent enable/disable/archive operations.

Logs may include agent, credential-record and realm UUIDs when access policy
allows, but never raw enrolment tokens, bearer secrets, full authorization
headers or unbounded payloads.

The agent similarly redacts credentials and sensitive probe configuration from
logs and diagnostic output.

## Required validation

- Enrolment token expiry, single use and atomic consumption.
- Recovery after a lost enrolment response.
- Credential authentication, revocation and safe rotation interruption.
- Cross-realm credential and configuration rejection.
- Compatible and incompatible protocol/schema versions.
- Deterministic configuration serialization and hashing.
- Durable activation before acknowledgement.
- Whole-snapshot rejection with last-known-good operation.
- Group membership changes producing affected configuration revisions.
- Capability conflicts remaining visible.
- Bounded payload, error and log behavior.
