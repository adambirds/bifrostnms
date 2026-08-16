# Realm tenancy

## Purpose

Realm tenancy is a foundational security and data-model boundary in BifrostNMS.
This document defines what belongs to an installation, what belongs to a realm,
and how code must enforce that separation.

A self-hosted installation may contain several realms even when its operator
uses only one. BifrostNMS Cloud uses the same model for many customer realms.
There must not be a separate single-tenant data model that later needs to be
converted for hosted use.

## Installation-wide identity

`User` is installation-wide. A person has one identity and may belong to several
realms through `RealmMembership` records:

```text
User
  |
  +-- RealmMembership -- Realm A
  |
  +-- RealmMembership -- Realm B
```

The following authentication records are also installation-wide because they
authenticate the user rather than access to one realm:

- WebAuthn credentials;
- TOTP methods and recovery codes; and
- authentication challenges.

Browser sessions are ephemeral Redis records. A session identifies the user and
stores an active realm selected from the realms that user may access.

## Realm-owned data

Persistent monitoring and operational resources are realm-owned. This includes:

- agents, agent groups, memberships and agent credentials;
- targets, target groups and memberships;
- monitors;
- direct and group-based monitor assignments;
- agent configuration state;
- observations and measurements;
- alert rules and alert state;
- notification channels;
- realm-scoped API credentials; and
- audit events concerning realm-owned resources.

Every such model must contain an explicit non-null `realm_id`. Realm ownership
must not be inferred only through a chain of relationships. This intentional
redundancy makes tenancy visible in schemas and enables efficient, reviewable
filtering of high-volume time-series data.

## Authorization boundaries

Normal realm access is granted through `RealmMembership`. The initial role names
are:

- `owner`;
- `admin`;
- `member`; and
- `viewer`.

The exact permissions attached to these roles require a separate authorization
design before monitoring-management APIs are exposed. Code must not scatter
role-name comparisons through route handlers.

`User.is_superuser` grants installation-wide administrative authority. It does
not create implicit membership rows and must not be used as a realm role.
Superuser access should remain explicit in authorization helpers and audit data.

## Query rules

An authenticated realm-owned request must establish an authorized realm before
loading the requested resource. The normal lookup shape is:

```python
resource = await Model.get_or_none(
    id=resource_id,
    realm_id=authorized_realm.id,
)
```

It must not load by globally unique ID first and check the realm only after using
the object. Collection queries, mutations, uniqueness checks and related-object
lookups must all include the realm boundary.

Services should accept an explicit realm or authorization context rather than
reading an ambient global value. Background tasks must carry a realm identifier
in their durable input and re-establish authorization or trusted system context
when they execute.

## Relationship integrity

Globally unique UUIDs prevent accidental identifier collisions, but they do not
prove that two resources belong to the same realm. Any relationship between two
realm-owned resources must validate matching `realm_id` values before it is
written.

For example, creating a monitor-agent assignment requires:

```text
assignment.realm_id == monitor.realm_id == agent.realm_id
```

This validation belongs in one domain service and runs inside the same database
transaction as the write. It must not be independently reimplemented by each
API route, importer or future Terraform endpoint.

Where Tortoise and PostgreSQL can express a practical database constraint for a
relationship, the Stage 3 migration should add it. Service validation and
realm-isolation tests remain required even when a database constraint exists.

## Uniqueness

Human-friendly names and slugs for realm-owned resources are unique within their
realm, not across the installation. Expected examples include:

```text
unique (realm_id, agent.name)
unique (realm_id, target.name)
unique (realm_id, monitor.name)
unique (realm_id, monitor_id, agent_id)
unique (realm_id, monitor_id, agent_group_id)
```

The existing realm slug is installation-wide because it is used to identify the
realm itself.

## Time-series tenancy

Observations and measurements must carry `realm_id` directly even when they also
carry realm-owned monitor and agent IDs. Monitoring queries nearly always begin
with a realm boundary; requiring a join merely to discover tenancy would make
isolation harder to review and high-volume queries less efficient.

Ingestion derives the authoritative realm from the authenticated agent. It must
not trust a realm identifier supplied as an unverified payload claim. The server
checks that referenced monitors and configuration revisions belong to the same
realm and agent before accepting observations.

The TimescaleDB design must make `realm_id` a leading part of relevant indexes
and retention/deletion procedures. Whether it is also a space-partitioning
dimension remains a measurement-design decision rather than an assumption here.

## Deletion and suspension

Realm suspension and realm deletion are different operations.

- Suspending a realm prevents normal access, configuration delivery and new
  ingestion without immediately deleting durable data.
- Deleting a realm is an explicit administrative workflow that must account for
  relational data, TimescaleDB data, Redis state, Celery work and agent
  credentials.

An ordinary ORM cascade is not an acceptable complete realm-deletion strategy.
The eventual deletion workflow must be resumable, auditable and safe for large
time-series volumes.

Monitoring entities are archived rather than immediately removed when history
refers to them. Archival prevents new scheduling while preserving historical
labels and relationships. Details are defined in `data-model.md`.

## API and automation implications

All management API paths must identify the active or explicit realm and enforce
the same authorization rules whether the caller is the dashboard, a script or a
future Terraform provider. There must be no privileged UI-only configuration
path.

List operations need deterministic filtering and pagination within one realm.
Create operations should support idempotency where unattended automation may
retry them. Read responses must never reveal another realm's existence through
different error details.

## Required Stage 3 tests

Before realm-owned models are considered complete, tests must prove that:

- users cannot read, modify or delete resources in another realm;
- duplicate names are rejected within one realm and allowed across realms;
- cross-realm relationships cannot be created;
- an agent cannot retrieve or submit data for another realm;
- superuser bypasses are explicit and audited rather than accidental;
- archived resources cannot receive new assignments or configuration; and
- suspension prevents new access and ingestion without destroying history.
