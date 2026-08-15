# Celery background tasks

BifrostNMS uses Celery for work that should not block an API request, including email delivery, notifications, and other asynchronous or scheduled application jobs.

## Architecture

Development uses the existing Redis service for three separate concerns, isolated by logical database:

- Redis DB 0: browser sessions and normal application Redis usage
- Redis DB 1: Celery broker
- Redis DB 2: Celery task result backend

The defaults are configured in `backend/bifrostnms/config.py` and can be overridden with:

```text
BIFROSTNMS_CELERY_BROKER_URL
BIFROSTNMS_CELERY_RESULT_BACKEND
BIFROSTNMS_CELERY_TASK_ALWAYS_EAGER
```

For production, these URLs may point at the same Redis deployment or at dedicated Redis services. Redis is a supported stable Celery broker.

## Code locations

- `backend/bifrostnms/celery_app.py`: Celery application and queue configuration
- `backend/bifrostnms/tasks/`: application task modules
- `backend/bifrostnms/tasks/system.py`: diagnostic health task

Queues are currently split into:

- `default`: normal background work
- `email`: email delivery
- `notifications`: notification delivery

Tasks matching `bifrostnms.tasks.email.*` and `bifrostnms.tasks.notifications.*` are automatically routed to their corresponding queue.

## Running locally

The VS Code tasks include a Celery worker and Celery Beat process. From a shell you can run them directly:

```bash
PYTHONPATH=backend celery -A bifrostnms.celery_app:celery_app worker \
  --loglevel=INFO \
  --queues=default,email,notifications
```

For scheduled tasks:

```bash
PYTHONPATH=backend celery -A bifrostnms.celery_app:celery_app beat \
  --loglevel=INFO
```

Beat is intentionally a separate process. Run exactly one Beat scheduler for a deployment unless a future scheduler implementation explicitly supports distributed leadership.

## Verifying the worker

With a worker running:

```bash
PYTHONPATH=backend celery -A bifrostnms.celery_app:celery_app inspect ping
```

To verify that a task travels through the broker and is executed by a worker:

```bash
PYTHONPATH=backend celery -A bifrostnms.celery_app:celery_app call \
  bifrostnms.tasks.system.healthcheck
```

The health task stores a short-lived result in Redis DB 2. Most fire-and-forget application tasks should use `ignore_result=True` unless the result is actually needed.

## Adding tasks

Place task code under `backend/bifrostnms/tasks/`. Keep task arguments serialisable as JSON primitives and identifiers; do not pass ORM model instances through Celery.

Prefer this pattern:

```python
@celery_app.task(name="bifrostnms.tasks.email.send_message", ignore_result=True)
def send_message(message_id: str) -> None:
    ...
```

Then enqueue from API/domain code:

```python
send_message.delay(str(message.id))
```

Tasks should be idempotent wherever practical because a task may be delivered more than once after worker failure. The worker is configured with late acknowledgement and rejection on worker loss for that reason.

## Tortoise ORM from Celery

Celery workers are not running inside FastAPI's lifespan and therefore do not inherit FastAPI's Tortoise context. A task that accesses PostgreSQL must explicitly initialise/use the application's Tortoise context. We will provide a shared task/database helper before the first database-backed Celery task rather than duplicating event-loop and connection setup in every task.

Do not call FastAPI request/session helpers from a Celery task; pass stable IDs and load the durable data the task needs.

## Tests

For unit tests that should execute tasks synchronously, set:

```text
BIFROSTNMS_CELERY_TASK_ALWAYS_EAGER=true
```

Eager mode is a test/development convenience and should remain disabled in normal deployments.
