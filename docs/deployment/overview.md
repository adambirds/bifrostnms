# Self-hosted deployment foundations

## Supported V1 topology

A self-hosted control plane consists of these independently restartable
processes:

- FastAPI API from `Dockerfile.backend`;
- one or more Celery workers from the same backend image;
- exactly one Celery Beat scheduler when scheduled control-plane tasks exist;
- dashboard from `Dockerfile.frontend`;
- authentication frontend from `Dockerfile.auth-frontend`;
- TimescaleDB 2.29 on PostgreSQL 17; and
- Redis for sessions, Celery broker data and task results.

The Go agent image is built from `Dockerfile.agent`, but agents run at monitoring
vantage points rather than as a required member of the control-plane stack.

The repository does not yet claim Kubernetes, Helm, Ansible or Terraform
deployment modules as supported. Their future implementations must preserve the
same process, migration, secret and persistence boundaries documented here.

## Startup and migration order

1. Start TimescaleDB and Redis and wait for their health checks.
2. Run `tools/db-migrate` once as a deployment job using the new backend image.
3. Verify the migration job completed successfully; never start with
   `BIFROSTNMS_AUTO_CREATE_SCHEMA=true`.
4. Start the API and Celery worker processes.
5. Start the auth and dashboard frontends.
6. Run API health, login, email and worker checks before admitting traffic.

Only one deployment job applies migrations. Multiple API replicas must not race
to migrate during startup. Back up persistent data before migrations whose
release notes identify meaningful schema or extension risk.

## Persistent state

| Service            | Persistent state                                    | Requirement                                                                 |
| ------------------ | --------------------------------------------------- | --------------------------------------------------------------------------- |
| TimescaleDB        | PostgreSQL data directory                           | Durable volume and tested backups are mandatory.                            |
| Redis              | Sessions and Celery state                           | Persistence is recommended when session/queued-task continuity is required. |
| API                | None                                                | Instances are replaceable after configuration and secrets are supplied.     |
| Celery worker/Beat | Beat schedule file only when file scheduler is used | Prefer an explicit small volume or a future database-backed scheduler.      |
| Next.js frontends  | None                                                | Instances are replaceable.                                                  |
| Agent              | SQLite configuration and observation queue          | Mount a durable writable volume at `/var/lib/bifrostnms-agent`.             |

Do not place PostgreSQL and agent SQLite data on ephemeral container layers.
Redis loss signs users out and may lose queued work; its persistence policy must
match the deployment's recovery objectives.

## Agent privileges

The agent image runs as the dedicated unprivileged `bifrostnms` user. Its
binary carries only the `CAP_NET_RAW` file capability required to open native
ICMP sockets; do not run the complete container as root or grant it the broader
`--privileged` mode. The container runtime and the filesystem holding the image
must preserve file capabilities.

Mount `/var/lib/bifrostnms-agent` as a writable volume owned by the container's
`bifrostnms` user. If an installation replaces the packaged binary, it must
grant that binary `cap_net_raw=ep` or supply the equivalent narrowly scoped
runtime capability. A missing capability is an agent operational error, not
packet loss or a target failure.

## Secrets

At minimum, provision these through a secret manager or mounted secret facility:

- PostgreSQL and Redis credentials;
- `BIFROSTNMS_AUTH_ENCRYPTION_KEY`;
- SMTP credentials or Microsoft Graph tenant/client/private-key material;
- TLS private keys at the reverse proxy; and
- future agent, API and notification credentials.

Non-secret public origins, RP identifiers, ports and feature configuration may
be ordinary deployment variables. Never put secret values in container images,
Compose files committed to Git, Terraform outputs/state visible to operators, or
Ansible command output. Restrict mounted secret files to the process user.

See `authentication.md` for the production authentication settings that the API
validates at startup and `../development/email.md` for email-provider secrets.

## Image validation

GitHub Actions builds and scans all currently supported application images:

- backend;
- dashboard frontend;
- authentication frontend; and
- Go agent.

Each component workflow runs source/dependency scanning, builds its Dockerfile
and scans the resulting image. A release must not be promoted when a required
build or configured severity gate fails. Database images are pinned separately
and must be reviewed through dependency updates rather than floating tags.

## Clean installation acceptance

A clean installation is dependable only when an operator can:

- start the pinned TimescaleDB and Redis services;
- apply every migration from an empty database;
- verify the `timescaledb` extension version;
- create the initial superuser with `tools/create-superuser`;
- start the API, worker and both frontends without schema auto-creation;
- send a test email through the configured provider; and
- sign in, select a realm and register a passkey at the public HTTPS origin.

Backend CI applies the complete migration chain to an empty pinned TimescaleDB
service and verifies the extension, preventing migration bootstrap regressions.
