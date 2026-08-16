# Production authentication deployment

## Required application settings

Set `BIFROSTNMS_ENV=production`. The API refuses to start unless these security
invariants hold:

- `BIFROSTNMS_COOKIE_SECURE=true`;
- `BIFROSTNMS_AUTH_ENCRYPTION_KEY` is deployment-specific and at least 32
  characters;
- `BIFROSTNMS_AUTH_FRONTEND_URL` uses HTTPS;
- `BIFROSTNMS_WEBAUTHN_ORIGIN` is the exact public HTTPS auth origin;
- `BIFROSTNMS_WEBAUTHN_RP_ID` is not `localhost`;
- `BIFROSTNMS_CORS_ORIGINS` contains explicit HTTPS origins, never `*`; and
- `BIFROSTNMS_AUTO_CREATE_SCHEMA=false`.

The WebAuthn origin includes scheme and port when non-default. The RP ID is a
registrable domain or an allowed parent domain and has no scheme or port. Changing
the RP ID after users register passkeys can make those credentials unusable.

Set `BIFROSTNMS_COOKIE_DOMAIN` only when the auth and dashboard applications need
one shared parent-domain cookie. Prefer host-only cookies when both applications
are served behind one public host. Cookies remain `HttpOnly` and `SameSite=Lax`.

## TLS and reverse proxies

Terminate TLS at a maintained reverse proxy or load balancer and forward requests
to the API over a protected network. Preserve the original host, scheme and
client address.

Uvicorn must trust forwarded headers only from known proxy addresses. Configure
its `FORWARDED_ALLOW_IPS` environment variable with explicit proxy IP/CIDR values.
Never use `*` on an API port that untrusted clients can reach directly. Without a
trusted proxy configuration, request client addresses in security audit events
describe the proxy connection rather than the original client.

The proxy should add or replace—not append untrusted incoming—`Forwarded` or
`X-Forwarded-*` headers. It should set HSTS after HTTPS operation is verified and
apply reasonable request-body/header limits without breaking WebAuthn payloads.

## Redis sessions

Redis contains browser sessions and must not be publicly reachable. Use network
isolation, authentication and encrypted transport when traffic crosses an
untrusted network. Production may use AOF or a managed persistence policy when
session continuity across Redis restarts is required.

The session token is an opaque bearer credential. It appears only in the browser
cookie; PostgreSQL and logs never store it. A Redis data loss signs users out but
does not damage persistent identities. Password resets invalidate existing
sessions using the user's persistent session version.

## Secrets and email links

Provide the authentication encryption key, database/Redis credentials, SMTP or
Microsoft Graph credentials and TLS private keys through the deployment secret
facility. Do not bake them into images, Terraform state output, Ansible logs or
repository files.

`BIFROSTNMS_AUTH_FRONTEND_URL` must be the external browser origin because it is
used for email verification and password-reset links. Validate outbound email and
link routing after deployment.

## Deployment verification

- Apply database migrations before starting the updated API.
- Confirm HTTP redirects to HTTPS and the session cookie has `Secure`, `HttpOnly`
  and `SameSite=Lax` attributes.
- Register and authenticate a test passkey from the public origin.
- Verify cross-origin API calls succeed only from configured frontend origins.
- Verify forwarded client addresses are correct and cannot be spoofed directly.
- Restart Redis and confirm behavior matches the chosen persistence policy.
- Exercise verification and password reset without exposing whether unknown
  accounts exist.
