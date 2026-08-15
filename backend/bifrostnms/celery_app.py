from celery import Celery
from kombu import Queue

from bifrostnms.config import get_settings

settings = get_settings()

celery_app = Celery(
    "bifrostnms",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "bifrostnms.tasks.system",
        "bifrostnms.tasks.email",
    ],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    task_default_queue="default",
    task_queues=(
        Queue("default"),
        Queue("email"),
        Queue("notifications"),
    ),
    task_routes={
        "bifrostnms.tasks.email.*": {"queue": "email"},
        "bifrostnms.tasks.notifications.*": {"queue": "notifications"},
    },
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
)

# Keep task discovery explicit. As BifrostNMS gains task modules, add them to
# Celery's include list above or import them from bifrostnms.tasks.

__all__ = ["celery_app"]
