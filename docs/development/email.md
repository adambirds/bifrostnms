# Email delivery

BifrostNMS sends application email asynchronously through Celery. The email layer is provider-neutral so application code does not need to know whether delivery uses SMTP or Microsoft Graph.

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
get_email_backend()
       / \
      /   \
 SMTP       Microsoft Graph
```

Select the provider with:

```env
BIFROSTNMS_EMAIL_BACKEND=smtp
```

or:

```env
BIFROSTNMS_EMAIL_BACKEND=microsoft_graph
```

The Celery task and all callers remain unchanged when the provider changes.

## SMTP

SMTP supports both authenticated and unauthenticated servers.

For an unauthenticated relay:

```env
BIFROSTNMS_EMAIL_BACKEND=smtp
BIFROSTNMS_SMTP_HOST=mail.internal.example
BIFROSTNMS_SMTP_PORT=25
BIFROSTNMS_SMTP_SECURITY=none
# BIFROSTNMS_SMTP_USERNAME=
# BIFROSTNMS_SMTP_PASSWORD=
BIFROSTNMS_SMTP_FROM_EMAIL=bifrostnms@example.com
BIFROSTNMS_SMTP_FROM_NAME=BifrostNMS
```

For authenticated SMTP:

```env
BIFROSTNMS_EMAIL_BACKEND=smtp
BIFROSTNMS_SMTP_HOST=smtp.example.com
BIFROSTNMS_SMTP_PORT=587
BIFROSTNMS_SMTP_SECURITY=starttls
BIFROSTNMS_SMTP_USERNAME=bifrostnms@example.com
BIFROSTNMS_SMTP_PASSWORD=replace-me
BIFROSTNMS_SMTP_FROM_EMAIL=bifrostnms@example.com
BIFROSTNMS_SMTP_FROM_NAME=BifrostNMS
```

If only one of username/password is configured, startup of the backend raises a configuration error rather than silently attempting unauthenticated delivery.

`BIFROSTNMS_SMTP_SECURITY` accepts `none`, `starttls`, or `ssl`. TLS certificate validation uses Python's default trusted certificate store.

## Microsoft Graph

The Microsoft Graph backend is based on the certificate-authenticated app-only pattern used by TechWiki, adapted behind BifrostNMS's provider-neutral email interface.

It uses Microsoft Entra client-credentials authentication and calls Microsoft Graph `POST /users/{sender}/sendMail`. The Entra application needs the Microsoft Graph **application** permission `Mail.Send` and administrator consent.

### App registration

Create or reuse an Entra app registration and record:

- Directory (tenant) ID
- Application (client) ID
- the dedicated mailbox/user principal name that BifrostNMS sends as

Upload the public X.509 certificate to the app registration under **Certificates & secrets > Certificates**. BifrostNMS keeps the corresponding private key.

For production, restrict the app's effective Exchange mailbox scope to the dedicated BifrostNMS sender mailbox where practical. `Mail.Send` application permission is otherwise broad.

### Configuration using mounted certificate files

This is the preferred self-hosted/production approach when Docker/Kubernetes secrets or another secret mount is available:

```env
BIFROSTNMS_EMAIL_BACKEND=microsoft_graph
BIFROSTNMS_MICROSOFT_GRAPH_TENANT_ID=<tenant-id>
BIFROSTNMS_MICROSOFT_GRAPH_CLIENT_ID=<client-id>
BIFROSTNMS_MICROSOFT_GRAPH_SENDER_EMAIL=bifrostnms@example.com
BIFROSTNMS_MICROSOFT_GRAPH_FROM_NAME=BifrostNMS
BIFROSTNMS_MICROSOFT_GRAPH_CERTIFICATE_PATH=/run/secrets/bifrostnms-graph.crt
BIFROSTNMS_MICROSOFT_GRAPH_PRIVATE_KEY_PATH=/run/secrets/bifrostnms-graph.key
BIFROSTNMS_MICROSOFT_GRAPH_PRIVATE_KEY_PASSPHRASE=
BIFROSTNMS_MICROSOFT_GRAPH_TIMEOUT_SECONDS=15
```

### Configuration using base64 environment values

As in TechWiki, both PEM credentials may instead be supplied as base64-encoded UTF-8. This is useful for deployment systems that inject text secrets through environment variables:

```env
BIFROSTNMS_EMAIL_BACKEND=microsoft_graph
BIFROSTNMS_MICROSOFT_GRAPH_TENANT_ID=<tenant-id>
BIFROSTNMS_MICROSOFT_GRAPH_CLIENT_ID=<client-id>
BIFROSTNMS_MICROSOFT_GRAPH_SENDER_EMAIL=bifrostnms@example.com
BIFROSTNMS_MICROSOFT_GRAPH_CERTIFICATE_BASE64=<base64-of-public-certificate-pem>
BIFROSTNMS_MICROSOFT_GRAPH_PRIVATE_KEY_BASE64=<base64-of-private-key-pem>
BIFROSTNMS_MICROSOFT_GRAPH_PRIVATE_KEY_PASSPHRASE=
```

Base64 values take precedence over file paths if both are configured.

Example commands to prepare one-line base64 values on Linux/macOS:

```bash
base64 < bifrostnms-graph.crt | tr -d '\n'
base64 < bifrostnms-graph.key | tr -d '\n'
```

Never commit the certificate private key, its passphrase, or base64-encoded private key to Git. Base64 is encoding, not encryption.

### Graph message format

BifrostNMS builds one normal RFC 5322/MIME message for both providers. Microsoft Graph receives the base64-encoded MIME representation, which preserves:

- plain-text and HTML alternatives
- multiple recipients
- `Reply-To`
- custom headers
- the same subject/body semantics as SMTP

A successful Graph `sendMail` request returns HTTP `202 Accepted`. That means Graph accepted the request for processing, not that final mailbox delivery has already completed.

## Sending application email

Always queue application email rather than calling a provider directly from an API request:

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

Connection-level failures and Microsoft Graph delivery failures are retried by Celery with exponential backoff, up to five retries.

Neither SMTP nor Microsoft Graph gives BifrostNMS a true exactly-once delivery guarantee. A worker can fail after the provider has accepted a message but before Celery acknowledges the task. Where duplicate notifications would be harmful, persist an outbound-message/event record and make delivery idempotent around that record.

## Test email

With the Celery worker running:

```bash
./tools/send-test-email you@example.com
```

or use the VS Code task **email: send test**.

The test goes through Celery and whichever backend is selected by `BIFROSTNMS_EMAIL_BACKEND`.

## Main code locations

- `backend/bifrostnms/email/base.py` — provider-neutral message model/protocol and MIME builder
- `backend/bifrostnms/email/smtp.py` — SMTP transport
- `backend/bifrostnms/email/microsoft_graph.py` — certificate-authenticated Microsoft Graph transport
- `backend/bifrostnms/email/__init__.py` — backend selection/factory
- `backend/bifrostnms/tasks/email.py` — Celery email task
- `backend/bifrostnms/cli/send_test_email.py` — test-email command
- `tools/send-test-email` — developer wrapper
- `backend/bifrostnms/config.py` — provider configuration

Business logic must depend on the provider-neutral email layer, not directly on SMTP, Graph, MSAL, or `requests`.
