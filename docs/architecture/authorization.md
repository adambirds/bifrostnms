# Realm authorization

## Purpose

This document defines the V1 realm role and permission contract. Authentication
establishes identity; authorization determines what that identity may do inside
the active realm. Route handlers must request named permissions through the
shared authorization helper and must not compare role strings themselves.

## Roles and permissions

Permissions are additive from viewer through owner, but the implementation uses
an explicit matrix rather than relying on role ordering.

| Permission                               | Owner | Admin | Member | Viewer |
| ---------------------------------------- | ----- | ----- | ------ | ------ |
| Read realm metadata                      | Yes   | Yes   | Yes    | Yes    |
| Read monitoring data/configuration       | Yes   | Yes   | Yes    | Yes    |
| Manage targets, monitors and assignments | Yes   | Yes   | Yes    | No     |
| Acknowledge alerts                       | Yes   | Yes   | Yes    | No     |
| Read realm memberships                   | Yes   | Yes   | No     | No     |
| Manage realm memberships                 | Yes   | Yes   | No     | No     |
| Manage agent enrolment credentials       | Yes   | Yes   | No     | No     |
| Change realm settings                    | Yes   | No    | No     | No     |
| Delete or transfer realm ownership       | Yes   | No    | No     | No     |

The named permission constants are:

```text
realm.read
realm.manage
realm.delete
members.read
members.manage
monitoring.read
monitoring.manage
agent_credentials.manage
alerts.acknowledge
```

An owner is the realm's accountable authority. Admins operate the realm and its
members but cannot transfer ownership, delete the realm or change owner-only
settings. Members can create and operate monitoring configuration but cannot
manage people or agent credentials. Viewers have read-only access.

## Request authorization

`require_realm_permission` performs these steps before a route loads a
realm-owned resource:

1. Authenticate the browser session.
2. Require an active realm identifier in the session.
3. Load that realm with `is_active=True`.
4. For a normal user, load the matching membership and validate its role.
5. Require the named permission from the explicit matrix.
6. Return a typed context containing user, session, realm, role and membership.

No active realm is a conflict that the client can resolve by selecting one.
Inactive/missing realms and missing memberships return the same not-found
response. This avoids revealing whether a realm exists to a user who cannot
access it. Unknown role values are denied rather than gaining fallback access.

Services receive the returned realm explicitly and scope every query with its
ID. Passing only a user or reading ambient session state inside domain services
is not sufficient.

## Installation superusers

Installation superusers may pass any realm permission for an active realm
without a membership row. The returned authorization context sets
`is_superuser_bypass` and leaves role/membership empty. Mutating APIs must copy
that fact into their audit event so installation authority never looks like
ordinary realm membership.

Superuser access does not bypass realm suspension. Operations that intentionally
administer a suspended realm require a separate installation-level endpoint and
`require_superuser` rather than the normal realm helper.

## Membership invariants

- Stored roles must be one of `owner`, `admin`, `member` or `viewer`.
- A realm must retain at least one owner.
- Removing or demoting the final owner is rejected transactionally.
- A user cannot change their own final-owner membership as a shortcut around
  ownership transfer.
- Membership changes invalidate an affected user's active realm access on their
  next authorized request even if their Redis session still names that realm.
- Cross-realm membership and resource identifiers are never accepted from a
  request merely because their UUIDs are valid.

Membership-management APIs and final-owner enforcement are implemented with the
realm management surface, not by scattering writes through authentication
routes.

## Testing requirements

- Every permission is allowed and denied according to the matrix.
- Missing, inactive and unauthorized realms do not leak cross-realm existence.
- Unknown roles fail closed.
- Superuser bypass is explicit in the returned context and audit record.
- Stage 3 resource tests prove all lookup and mutation queries use the context's
  realm ID.
- Membership tests prove a realm cannot lose its final owner.
