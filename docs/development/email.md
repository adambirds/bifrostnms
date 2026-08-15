# Email delivery

BifrostNMS sends application email asynchronously through Celery. The default transport is SMTP and supports both authenticated and unauthenticated SMTP servers.

## Architecture

```text
FastAPI / application code
        |
        | send_email.delay(...)
        v
Redis DB 1 (Celery broker)
        |
        v
Celery email queue
        |
        v
SMTPEmailBackend
        |
        v
SMTP server
```

Email tasks are routed to the `email` Celery queue. The worker started by the development task listens to `default,email,notifications`.

## SMTP authentication

Authentication is optional.

For an unauthenticated relay, leave both credentials unset:

```env
BIFROSTNMS_SMTP_HOST=mail.internal.example
BIFROSTNMS_SMTP_PORT=25
BIFROSTNMS_SMTP_SECURITY=none
# BIFROSTNMS_SMTP_USERNAME=
# BIFROSTNMS_SMTP_PASSWORD=
```

For authenticated SMTP, set both values:

```env
BIFROSTNMS_SMTP_HOST=smtp.example.com
BIFROSTNMS_SMTP_PORT=587
BIFROSTNMS_SMTP_SECURITY=starttls
BIFROSTNMS_SMTP_USERNAME=bifrostnms@example.com
BIFROSTNMS_SMTP_PASSWORD=replace-me
```

If only one of username/password is configured, the SMTP backend raises a configuration error rather than silently attempting unauthenticated delivery.

## Transport security

`BIFROSTNMS_SMTP_SECURITY` accepts:

- `none` — plain SMTP, usually port 25. This can still be appropriate for a trusted local relay inside a private network.
- `starttls` — connect using SMTP and upgrade the connection with STARTTLS, usually port 587.
- `ssl` — implicit TLS from connection establishment, usually port 465.

TLS certificate validation uses Python's default trusted certificate store.

## Configuration

```env
BIFROSTNMS_SMTP_HOST=localhost
BIFROSTNMS_SMTP_PORT=25
BIFROSTNMS_SMTP_SECURITY=none
BIFROSTNMS_SMTP_TIMEOUT_SECONDS=15
BIFROSTNMS_SMTP_FROM_EMAIL=bifrostnms@localhost
BIFROSTNMS_SMTP_FROM_NAME=BifrostNMS
```

Optional authentication:

```env
BIFROSTNMS_SMTP_USERNAME=
BIFROSTNMS_SMTP_PASSWORD=
```

Do not commit real SMTP credentials. Production deployments should inject them through environment variables or their secret-management system.

## Sending application email

Use the Celery task rather than calling SMTP directly from an API request:

```python
from bifrostnms.tasks.email import send_email

send_email.delay(
    to=["user@example.com"],
    subject="Welcome to BifrostNMS",
    text="Your account is ready.",
    html="<p>Your account is <strong>ready</strong>.</p>",
)
```

The task accepts JSON-serialisable values only. Do not pass Tortoise model instances through Celery.

For workflows whose contents depend on durable database state, prefer passing an ID and loading the current record in the task once the shared Celery/Tortoise database helper exists.

## Retries and idempotency

SMTP delivery retries automatically for connection-level `OSError` and timeout failures with exponential backoff, up to five retries.

SMTP itself does not provide exactly-once delivery. A worker can fail after the remote SMTP server accepted a message but before Celery acknowledged the task. Email-generating workflows should therefore be designed with duplicate-delivery risk in mind. Where duplicate notifications would be harmful, persist an outbound-message/event record and make delivery idempotent around that record.

## Test email

With the Celery worker running:

```bash
./tools/send-test-email you@example.com
```

or:

```bash
./tools/send-test-email you@example.com --subject "SMTP check"
```

This queues the test message through Celery; it does not bypass the background-job path.

## Main code locations

- `backend/bifrostnms/email/smtp.py` — SMTP transport and message construction
- `backend/bifrostnms/tasks/email.py` — Celery email task
- `backend/bifrostnms/cli/send_test_email.py` — test-email command
- `tools/send-test-email` — developer wrapper
- `backend/bifrostnms/config.py` — SMTP configuration

The transport is intentionally isolated from callers so BifrostNMS Cloud can later introduce another email provider without changing authentication/notification business logic.
