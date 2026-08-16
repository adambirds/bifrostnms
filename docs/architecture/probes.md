# Native probe framework and V1 probes

## Purpose

This document defines the common Go probe contract and the behavior of the five
V1 probe families. It is the bridge between monitor configuration, agent
scheduling and the typed results in `measurements.md`.

Standard probes are native Go implementations. They must not shell out to
`ping`, `fping`, `curl`, `dig`, `openssl`, `nc` or `traceroute`.

## Probe framework

Each probe implementation provides the conceptual interface:

```go
type Probe interface {
	Type() ProbeType
	ConfigurationSchemaVersion() uint32
	ResultSchemaVersion() uint32
	Validate(raw json.RawMessage) error
	Run(ctx context.Context, request Request) Result
}
```

The exact Go package names may change, but these responsibilities must remain
separate:

- configuration decoding and validation;
- scheduling;
- protocol execution;
- result calculation;
- durable observation serialization; and
- synchronization.

A probe returns one result to the scheduler. It does not write SQLite, call the
control plane or update global health directly.

## Common request

The scheduler supplies:

```text
observation_id
scheduled_at
agent_config_revision
monitor_id
monitor_revision
target_id
target_address
timeout
typed probe configuration
```

The scheduler creates a context whose deadline implements the monitor timeout.
Probe implementations must honor cancellation and must close response bodies,
connections and other resources on every path.

Target addresses come from the validated configuration snapshot. A probe does
not make an API request to discover additional configuration while running.

## Common result

Every probe returns:

```text
started_at
finished_at
execution_status
assessment
error_category
error_code
bounded error_message
typed probe result
```

Durations use Go's monotonic clock. Wall-clock timestamps are serialized in UTC
with sufficient precision and validated later by ingestion.

Expected target/protocol failures produce completed observations with an
unhealthy assessment whenever the probe gathered enough evidence to make that
assessment. Local permission, invalid runtime configuration, resource exhaustion
or internal failures produce failed/unknown observations.

Errors are wrapped into stable probe-owned codes. Raw library or operating-system
messages may be useful locally but are not uploaded without bounding and
redaction.

## Configuration schemas

Every probe configuration has its own versioned JSON schema represented by a
strict Pydantic model in the control plane and matching Go type in the agent.

Rules include:

- unknown fields are rejected for an active schema version;
- durations use integer milliseconds or seconds as named by the field, never
  ambiguous strings in the wire contract;
- defaults are materialized into the immutable agent snapshot;
- hostnames, ports, paths and record types are validated before delivery;
- numeric values are finite and within documented bounds; and
- secrets are references to a secret facility, never arbitrary plaintext fields
  added to generic JSON.

The server validates first, but the agent validates independently before
activating a complete snapshot.

## Scheduler behavior

The scheduler operates from the last valid local configuration and maintains one
logical job for every effective monitor assignment.

V1 scheduling rules are:

- interval is measured from scheduled times rather than completion times;
- one assignment does not overlap its previous execution;
- if an execution is still running at the next scheduled time, that occurrence
  is missed and reported as scheduler/coverage state rather than queued forever;
- restarts do not replay every schedule instant that elapsed while the process
  was stopped;
- the next due time is persisted sufficiently to avoid a restart burst;
- cancellation uses the monitor timeout and agent shutdown context; and
- bounded worker pools prevent configuration size from creating unbounded
  goroutines.

Initial monitor interval bounds are 5 seconds to 24 hours. Timeout must be at
least 100 milliseconds and shorter than the interval. Individual probe schemas
may require stricter bounds.

Agents apply deterministic bounded jitter derived from assignment identity so
thousands of monitors do not all execute at the same instant. Jitter never moves
an execution outside a documented fraction of its interval and does not change
the logical `scheduled_at` bucket unpredictably.

Concurrency limits are agent configuration, not monitor-controlled unbounded
values. Separate protocol families may have separate pools because raw ICMP and
HTTP have different resource behavior.

## Network resolution

Hostname resolution occurs at the agent vantage point. This preserves split-
horizon DNS, local search behavior and geographically dependent answers.

Probes record the selected address where useful. V1 does not attempt every
resolved address in parallel unless the probe contract says so. Address-family
selection and fallback behavior must be deterministic and testable.

The agent supports IPv4 and IPv6 capabilities independently and reports them to
the control plane.

## ICMP probe

### Configuration

```text
packet_count               integer, default 20, range 1..100
packet_interval_ms         integer, default 50, range 10..1000
per_packet_timeout_ms      integer, default derived from monitor timeout
payload_size_bytes         integer, default 56, bounded by safe MTU policy
address_family             auto | ipv4 | ipv6
```

The total packet sequence must fit inside the monitor timeout. Validation rejects
a configuration whose count, interval and per-packet timeout cannot do so.

V1 ICMP measures echo request/reply. It records successful RTT values in packet
sequence order and sent/received counts. It does not invoke a system ping binary.

Linux packaging grants only the network capability required for ICMP (normally
`CAP_NET_RAW`) rather than running the complete agent as root. Other platforms
use their supported native socket behavior and advertise availability through
capabilities.

### Calculations

For successful RTT samples sorted by value:

- minimum and maximum are the first and last values;
- average is arithmetic mean;
- percentile `p` uses index `(n - 1) * p` with linear interpolation between the
  surrounding samples;
- median is percentile `0.5`;
- p95 is percentile `0.95`; and
- jitter is the arithmetic mean of absolute differences between consecutive
  successful RTTs in packet sequence order.

With fewer than two successful samples, jitter is null. With no successful
samples, latency summaries are null rather than zero.

Packet loss is:

```text
100 * (packets_sent - packets_received) / packets_sent
```

The agent returns individual successful RTTs plus summaries. The server can
verify summaries within a documented floating-point tolerance.

### Assessment

The default assessment is healthy when at least one configured reply succeeds.
Monitor configuration may set packet-loss and latency thresholds that make the
result unhealthy. Complete loss is completed/unhealthy, not a local execution
failure.

Permission or unsupported-socket errors are failed/unknown with a stable
capability error.

## HTTP/HTTPS probe

HTTP and HTTPS share one probe type. Scheme controls TLS use.

### Configuration

```text
scheme                     http | https
port                       nullable integer, defaults by scheme
path                       string beginning with '/', default '/'
method                     GET | HEAD, default GET
follow_redirects           boolean, default true
maximum_redirects          integer, default 5, range 0..10
host_header                nullable validated hostname
request_headers            bounded map of permitted non-secret headers
expected_status_codes      bounded integer list, default 200..399
expected_header_values     bounded typed assertions
expected_body_contains     bounded list of strings
maximum_response_bytes     integer, default 1 MiB, bounded
address_family             auto | ipv4 | ipv6
```

V1 does not support arbitrary request bodies or plaintext authentication secrets
inside monitor JSON. Headers such as `Authorization`, `Cookie`, and proxy
credentials are rejected unless a future secret-reference design explicitly
supports them.

The probe constructs the URL from scheme, target address, optional port and path.
It rejects control characters, invalid paths and credentials embedded in URLs.

HTTPS uses the platform/agent trust store and verifies certificate chain and
hostname. V1 does not provide a per-monitor “ignore all TLS errors” switch.
Deployments with private PKI configure trusted CAs through a documented agent-
level trust mechanism without embedding private key material in monitor config.

### Timings

Using Go HTTP tracing, record where available:

```text
DNS resolution
TCP connection
TLS handshake
time to first response byte
total request duration
```

Redirect timing is total across the followed request chain. Detailed per-hop
timings are deferred; redirect count and a redacted final URL are retained.

The probe reads at most `maximum_response_bytes`. It may stop after all bounded
body assertions are decidable. Response bodies are never stored in observations
or uploaded in errors.

### Assessment

Network/TLS/protocol completion, status expectations and configured assertions
determine healthy/unhealthy. An unexpected HTTP status is completed/unhealthy.
A local inability to create the request or enforce safe configuration is
failed/unknown.

## TCP connect probe

### Configuration

```text
port                       integer, range 1..65535
address_family             auto | ipv4 | ipv6
```

The probe performs a native TCP connection using a context-aware dialer, records
the selected address and connection duration, and closes the connection
immediately after success.

Connection refusal, network unreachable and timeout are completed/unhealthy with
distinct stable error codes. Local resource or invalid-runtime errors are
failed/unknown.

V1 does not send application payloads through the TCP probe; protocol-specific
checks belong to dedicated probes.

## DNS probe

### Configuration

```text
resolver_mode              system | explicit
resolver_address           required for explicit mode
resolver_port              default 53
transport                  udp_with_tcp_fallback | tcp
query_name                 nullable, defaults to target address
query_type                 A | AAAA | CNAME | MX | NS | TXT | PTR
recursion_desired          boolean, default true
expected_response_codes    bounded list, default NOERROR
expected_answers           bounded typed assertions
```

Explicit resolver mode measures a query against the named resolver. System mode
uses the agent's configured resolver behavior and records that no single explicit
resolver address was selected when the platform cannot expose it.

The native DNS implementation sends UDP by default and retries over TCP when the
response is truncated. It bounds answer count, record length and total message
size before serialization.

The result stores normalized typed answer data. TXT and other records remain
bounded; malformed or oversized responses cannot cause unbounded observation
payloads.

NXDOMAIN or another valid DNS response is completed and assessed against the
expected response codes. Resolver timeout is completed/unhealthy. A local
configuration or parser invariant failure is failed/unknown.

## TLS certificate probe

### Configuration

```text
port                       integer, default 443
server_name                nullable, defaults to target hostname
address_family             auto | ipv4 | ipv6
minimum_tls_version        default TLS 1.2
expiry_warning_days        integer, default 30, range 0..3650
```

An IP target that requires hostname validation must supply `server_name`.
Validation rejects an empty server name when no meaningful hostname can be
derived.

The probe performs a native TLS handshake using the agent trust store and records
the negotiated protocol/cipher plus bounded leaf-certificate metadata. It
validates chain, hostname and validity dates.

Certificate expiry threshold assessment is separate from handshake execution:

- a valid certificate outside the warning window is healthy;
- a valid certificate inside the warning window is unhealthy according to the
  configured threshold;
- expired, untrusted or hostname-mismatched certificates are
  completed/unhealthy with distinct codes; and
- local TLS/runtime failures that prevent trustworthy assessment are
  failed/unknown.

Full chains and certificate bodies are not included in every observation.

## Secrets and privacy

Probe configuration and result logging must assume targets can be sensitive.

- Never log raw credentials, cookies, authorization headers or request bodies.
- Redact URL user information, sensitive query values and configured headers.
- Never store HTTP response bodies as observation data.
- Bound DNS answers, certificate names and remote error text.
- Do not expose one realm's target information through capability/configuration
  errors returned to another agent.

Secret-backed HTTP authentication and client certificates require a separate
realm-owned secret-reference design and are post-V1 unless promoted explicitly.

## Capability mapping

An agent advertises each probe and supported configuration/result schema
versions. Runtime requirements are advertised independently:

```text
icmp schema 1 + raw_socket false
```

means the binary understands ICMP schema 1 but cannot currently execute it.

The server validates assignments against both schema and runtime capability. A
runtime capability can change after deployment; losing it produces visible
configuration/probe state and does not silently remove historical assignments.

## Testing strategy

Probe tests must be deterministic and avoid public Internet dependencies.

- ICMP calculation tests use recorded synthetic reply sequences; privileged
  socket integration tests run only in an explicit capable environment.
- HTTP/HTTPS tests use local servers, controlled redirects, delayed phases and
  generated test certificates.
- TCP tests use local listeners and controlled refusal/timeout scenarios.
- DNS tests use a local authoritative/resolver fixture with bounded crafted
  messages and TCP fallback.
- TLS tests use local servers with valid, expired, mismatched and untrusted test
  chains.

Shared contract tests run the same canonical configuration/result fixtures
through Python and Go representations to prevent schema drift.

Fuzz tests are appropriate for configuration decoding, DNS result parsing,
bounded HTTP assertions and observation serialization.

## Required validation

- Every V1 probe satisfies the common interface and cancellation contract.
- Unknown configuration fields and unsupported schema versions are rejected.
- Timeouts release all resources and do not leak goroutines.
- Scheduler concurrency remains bounded under large configuration.
- Missed/overlapping schedules affect coverage without creating a replay storm.
- ICMP statistics match the specified algorithms and preserve raw RTTs.
- HTTP never stores response bodies or sensitive headers.
- DNS parsing and answer serialization remain bounded.
- TLS distinguishes expiry, trust and hostname failures.
- IPv4/IPv6 and runtime capability behavior is explicit.
- Python and Go contract fixtures agree.
- Standard operation invokes no external probe executables.
