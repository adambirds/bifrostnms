# Audit events

## Purpose

BifrostNMS records security and administrative actions as structured audit
events. Audit events explain who attempted an action, where it applied, whether
it succeeded and whether installation-superuser authority bypassed normal realm
membership. They are not application debug logs or a copy of request bodies.

## Storage and tenancy

`AuditEvent` is an append-only PostgreSQL record with:

```text
id
occurred_at
realm_id (nullable)
actor_user_id (nullable)
actor_type
action
outcome
target_type / target_id
source_ip / bounded user_agent
superuser_bypass
bounded metadata
```

Realm-owned actions always set `realm_id`. Installation-wide authentication
events may omit it. Actor and realm foreign keys use `SET NULL` so deleting an
identity does not erase the security history; target identifiers are durable
strings because monitored objects may later be purged.

Application code may create events only through the centralized audit writer.
Ordinary APIs never update or delete an event. A future retention job may delete
expired events under an explicit installation policy; that maintenance action
is itself audited.

## Required event families

Initial authentication and realm administration must cover:

- signup and email verification;
- successful and failed login, including 2FA and passkey methods;
- logout and password reset;
- TOTP/passkey/recovery-code lifecycle changes;
- realm activation failures when they represent denied access;
- membership invitation, role change and removal;
- ownership transfer;
- agent enrolment-token and credential lifecycle;
- realm suspension, reactivation and deletion workflow; and
- every mutating operation performed through superuser bypass.

High-volume probe observations, ordinary reads and session refreshes are not
audit events. Operational telemetry covers those paths.

## Privacy and secret handling

Audit metadata contains identifiers, changed field names and safe decision
context—not arbitrary serialized inputs. The writer rejects metadata keys that
look like passwords, tokens, secrets, credentials, cookies or authorization
headers, including nested keys.

Never record:

- plaintext passwords, recovery codes or TOTP secrets;
- raw session, verification, reset, enrolment or API tokens;
- WebAuthn challenge or credential payloads;
- authorization/cookie headers;
- email bodies or HTTP probe bodies; or
- encrypted secret material merely because it is encrypted.

IP addresses and user agents are personal/security data. Access and retention
must follow the installation's declared privacy policy.

## Failure behavior

For security-sensitive mutations, the domain change and audit insert should
share a database transaction so neither can succeed alone. Authentication
failure auditing must not change the response or disclose account existence.

An audit storage outage is not silently ignored for administrative mutations.
Read-only health/status paths may remain available, but privileged changes fail
closed until their audit record can be persisted.

## Query and retention requirements

Audit APIs are installation-superuser or realm-owner/admin surfaces and always
filter by an authorized realm before target identifiers. Results are ordered by
`occurred_at` plus `id`, use bounded pagination and can filter by action,
outcome, actor and time range.

V1 retains audit events for at least one year by default. The exact configurable
retention and export mechanism belongs to the operational implementation. Audit
retention is independent from monitoring-observation retention.

## Validation

- Realm audit queries cannot reveal another realm's events.
- Actor/realm deletion preserves the event with nullable foreign keys.
- Sensitive nested metadata keys are rejected.
- User-agent length is bounded and source address parsing is proxy-aware only
  after trusted-proxy configuration is established.
- Superuser mutations always set `superuser_bypass`.
- Transactional mutation tests prove audit failure prevents the domain change.
