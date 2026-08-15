from bifrostnms.celery_app import celery_app
from bifrostnms.tasks.system import healthcheck


def test_celery_queues_and_routes_are_configured():
    queues = {queue.name for queue in celery_app.conf.task_queues}

    assert {"default", "email", "notifications"}.issubset(queues)
    assert celery_app.conf.task_default_queue == "default"
    assert celery_app.conf.task_routes["bifrostnms.tasks.email.*"]["queue"] == "email"
    assert celery_app.conf.task_routes["bifrostnms.tasks.notifications.*"]["queue"] == "notifications"


def test_celery_reliability_defaults():
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.accept_content == ["json"]


def test_healthcheck_task():
    assert healthcheck.run() == {"status": "ok"}
