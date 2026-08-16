# Local development

The recommended environment is the repository Dev Container.

## Services

- FastAPI: `http://localhost:8000`
- Dashboard (Next.js 16): `http://localhost:3000`
- Auth frontend (Next.js 16): `http://localhost:3001`
- PostgreSQL: `postgres:5432` inside Compose
- Redis: `redis:6379` inside Compose

## First run

```bash
./tools/db-bootstrap
```

Then start each application in separate terminals:

```bash
uvicorn backend.bifrostnms.main:app --host 0.0.0.0 --port 8000 --reload
pnpm --dir auth-frontend dev
pnpm --dir frontend dev
```

## Environment

Development defaults are in `.devcontainer/.env.example`. Important auth-related variables are:

```text
BIFROSTNMS_DATABASE_URL
BIFROSTNMS_REDIS_URL
BIFROSTNMS_AUTH_ENCRYPTION_KEY
BIFROSTNMS_AUTH_FRONTEND_URL
BIFROSTNMS_EMAIL_VERIFICATION_TTL_HOURS
BIFROSTNMS_PASSWORD_RESET_TTL_MINUTES
BIFROSTNMS_WEBAUTHN_RP_ID
BIFROSTNMS_WEBAUTHN_RP_NAME
BIFROSTNMS_WEBAUTHN_ORIGIN
BIFROSTNMS_SESSION_TTL_DAYS
BIFROSTNMS_AGENT_ENROLMENT_TTL_MINUTES
BIFROSTNMS_AGENT_HEARTBEAT_INTERVAL_SECONDS
BIFROSTNMS_AGENT_OFFLINE_AFTER_SECONDS
BIFROSTNMS_AGENT_CONFIGURATION_POLL_INTERVAL_SECONDS
```

Never use the development encryption key in production.

## Authentication UI

Create an account or sign in at `http://localhost:3001`. The auth app and dashboard share the same host-scoped `HttpOnly` session cookie even though they run on different ports.

Passkeys work on localhost because browsers treat localhost as a secure development context. Production passkeys require HTTPS and correct RP ID/origin configuration.

## GitHub CLI authentication

The Dev Container mounts `/root/.config/gh` from the named Docker volume
`bifrostnms-github-cli-config`. After authenticating once with:

```bash
gh auth login
```

the GitHub CLI credentials survive normal Dev Container rebuilds. They remain
outside the repository and are not included in the container image.

Removing the named volume, deleting all project Dev Container volumes or running
`gh auth logout` removes the persisted authentication and requires a new login.
