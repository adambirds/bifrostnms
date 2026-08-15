# Authentication architecture

BifrostNMS has a dedicated authentication frontend (`auth-frontend/`) and a FastAPI authentication API under `/api/v1/auth`.

## Persistent vs ephemeral authentication data

Persistent identity/security data is stored in PostgreSQL through Tortoise ORM:

- `User`
- `Realm`
- `RealmMembership`
- `WebAuthnCredential`
- `TwoFactorMethod`
- `RecoveryCode`
- short-lived WebAuthn/2FA challenge records for now

Browser sessions are deliberately stored in Redis, not PostgreSQL.

## Session flow

1. Password, password+TOTP/recovery-code, or passkey authentication succeeds.
2. FastAPI generates a cryptographically random opaque session token.
3. Only the token hash is used to build the Redis key: `bifrostnms:session:<sha256>`.
4. Redis stores session metadata as JSON with an expiry equal to `BIFROSTNMS_SESSION_TTL_DAYS`.
5. The raw token is sent only to the browser in the `HttpOnly` `bifrost_session` cookie.
6. Each authenticated request hashes the cookie value, reads the corresponding Redis session, loads the user from PostgreSQL, refreshes `last_activity`, and extends the Redis TTL.
7. Logout deletes the Redis key and expires the cookie.

A Redis flush/restart without persistence therefore signs users out; it does not corrupt identity data. Production deployments may use Redis AOF/managed persistence if session continuity across Redis restarts is desired.

## Realm context

A session stores `active_realm_id`. `User` is global to an installation; normal access to a realm is defined by `RealmMembership`. Realm switching validates membership before changing the Redis session.

Installation superusers are the exception: they have implicit installation-wide access and may activate any active realm even without a `RealmMembership` row. This keeps platform administration separate from customer/user realm roles.

## Installation superusers

`User.is_superuser` is the installation-wide administrative flag. BifrostNMS intentionally does not have Django-style `is_staff`; there is no separate Django Admin-equivalent permission to model.

A superuser:

- may administer the whole BifrostNMS installation;
- has implicit access to every active realm;
- remains distinct from realm roles such as `owner`, `admin`, `member`, and `viewer`;
- is returned by the authentication API with `is_superuser: true`.

Create a new superuser inside the Dev Container with:

```bash
./tools/create-superuser
```

You can pre-supply identity fields:

```bash
./tools/create-superuser \
  --email admin@example.com \
  --first-name Admin \
  --last-name User
```

The password is prompted without echoing. For automated deployment, set `BIFROSTNMS_SUPERUSER_PASSWORD` for the command invocation rather than passing a password on the command line.

To promote an existing account:

```bash
./tools/create-superuser \
  --email existing@example.com \
  --promote-existing
```

Code that requires installation-wide privileges should use `backend/bifrostnms/auth/permissions.py::require_superuser` rather than duplicating flag checks in individual endpoints.

## Passwords

Passwords are hashed with `pwdlib` using its recommended Argon2 configuration. Password hashes are stored in PostgreSQL. Plaintext passwords are never stored.

## TOTP two-factor authentication

TOTP secrets are generated with `pyotp`. The TOTP secret is encrypted before storage using Fernet; `BIFROSTNMS_AUTH_ENCRYPTION_KEY` must be a strong deployment-specific secret in production. Recovery codes are generated once and only their SHA-256 hashes are stored.

Password login for a user with TOTP enabled does not create a session immediately. It creates a short-lived 2FA challenge; only successful TOTP or recovery-code verification creates the Redis session.

## WebAuthn/passkeys

BifrostNMS uses the maintained `webauthn` Python package for WebAuthn ceremony generation and cryptographic verification. We own the API and data model, but do not hand-roll CBOR parsing, signature verification, RP ID checking, or authenticator validation.

Important deployment settings:

- `BIFROSTNMS_WEBAUTHN_RP_ID`
- `BIFROSTNMS_WEBAUTHN_RP_NAME`
- `BIFROSTNMS_WEBAUTHN_ORIGIN`

Production WebAuthn requires a secure HTTPS origin.

## Main code locations

- `backend/bifrostnms/api/auth.py` - signup/login/logout/current-user/realm switching
- `backend/bifrostnms/api/two_factor.py` - TOTP and recovery-code API
- `backend/bifrostnms/api/webauthn.py` - passkey API
- `backend/bifrostnms/auth/security.py` - password and Redis session implementation
- `backend/bifrostnms/auth/permissions.py` - installation-level authorization helpers
- `backend/bifrostnms/auth/two_factor.py` - TOTP/recovery-code logic
- `backend/bifrostnms/auth/webauthn.py` - WebAuthn ceremony logic
- `backend/bifrostnms/models/auth.py` - persistent authentication models
- `backend/bifrostnms/cli/create_superuser.py` - superuser administration CLI
- `auth-frontend/` - Next.js authentication application
