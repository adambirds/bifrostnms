# Authentication architecture

BifrostNMS has a dedicated authentication frontend (`auth-frontend/`) and a FastAPI authentication API under `/api/v1/auth`.

The main dashboard deliberately does not own account-security UI. Authenticated users follow the **Account** link in the dashboard to the auth frontend, where identity and security settings are managed centrally.

## Frontend routes

The authentication frontend provides:

- `/login` - password, passkey and 2FA/recovery-code sign-in flow;
- `/signup` - account creation;
- `/logout` - session termination;
- `/forgot-password` - non-enumerating password-reset request;
- `/reset-password` - password reset from an emailed one-time link;
- `/verify-email` - email confirmation from an emailed one-time link;
- `/account` - authenticated account overview;
- `/security` - authenticated TOTP, recovery-code and passkey management.

`/account` and `/security` perform a server-side `/api/v1/auth/me` check before rendering. If the shared session is missing or expired, the user is redirected to `/login` with the requested auth page preserved in `next=`.

The dashboard links to `${NEXT_PUBLIC_AUTH_URL}/account`. The auth account shell links back to `NEXT_PUBLIC_DASHBOARD_URL`, so the two Next.js applications remain separate while sharing the same FastAPI/Redis browser session.

When the auth frontend runs separately from the API in production, set `BIFROST_API_INTERNAL_URL` to the API URL reachable by the auth frontend's Next.js server process.

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

## Email verification and password recovery

Signup creates an email-verification challenge and sends its link through the
configured Celery email queue. Authenticated users may request another link from
the account page. Password-reset requests always return the same accepted
response, including for unknown or disabled accounts, so the endpoint does not
disclose whether an address is registered.

Both flows use cryptographically random, expiring, single-use tokens. Only a
SHA-256 token hash is stored in PostgreSQL. Issuing another token consumes older
outstanding tokens of the same type. Verification links expire after
`BIFROSTNMS_EMAIL_VERIFICATION_TTL_HOURS`; password-reset links expire after
`BIFROSTNMS_PASSWORD_RESET_TTL_MINUTES`.

`BIFROSTNMS_AUTH_FRONTEND_URL` is the public browser URL used to construct both
links. It must be the externally reachable HTTPS auth-frontend origin in
production, not the API's internal container address.

Every password reset increments the user's persistent session version. Redis
sessions carry the version present when they were created and are rejected on
their next use when it no longer matches, signing out all existing sessions
without storing raw session tokens in PostgreSQL.

## TOTP two-factor authentication

TOTP secrets are generated with `pyotp`. The TOTP secret is encrypted before storage using Fernet; `BIFROSTNMS_AUTH_ENCRYPTION_KEY` must be a strong deployment-specific secret in production. Recovery codes are generated once and only their SHA-256 hashes are stored.

Password login for a user with TOTP enabled does not create a session immediately. It creates a short-lived 2FA challenge; only successful TOTP or recovery-code verification creates the Redis session.

The `/security` page allows an authenticated user to configure an authenticator app, verify setup, receive recovery codes, inspect the number of unused recovery codes, and disable TOTP.

## WebAuthn/passkeys

BifrostNMS uses the maintained `webauthn` Python package for WebAuthn ceremony generation and cryptographic verification. We own the API and data model, but do not hand-roll CBOR parsing, signature verification, RP ID checking, or authenticator validation.

The `/security` page allows an authenticated user to register, name, view and remove passkeys. The login page supports passwordless passkey authentication.

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
- `backend/bifrostnms/auth/account_lifecycle.py` - verification and reset tokens
- `backend/bifrostnms/auth/permissions.py` - installation-level authorization helpers
- `backend/bifrostnms/auth/two_factor.py` - TOTP/recovery-code logic
- `backend/bifrostnms/auth/webauthn.py` - WebAuthn ceremony logic
- `backend/bifrostnms/models/auth.py` - persistent authentication models
- `backend/bifrostnms/cli/create_superuser.py` - superuser administration CLI
- `auth-frontend/src/app/account/` - authenticated account overview
- `auth-frontend/src/app/security/` - authenticated security settings route
- `auth-frontend/src/app/forgot-password/` - reset request route
- `auth-frontend/src/app/reset-password/` - password reset route
- `auth-frontend/src/app/verify-email/` - email verification route
- `auth-frontend/src/components/SecuritySettings.tsx` - TOTP/passkey management UI
- `auth-frontend/src/lib/server-auth.ts` - server-side account-route session guard
