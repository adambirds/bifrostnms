from bifrostnms.celery_app import celery_app


@celery_app.task(  # type: ignore[untyped-decorator]
    name="bifrostnms.tasks.system.healthcheck",
    ignore_result=False,
)
def healthcheck() -> dict[str, str]:
    """Small diagnostic task used to verify the Celery worker end-to-end."""

    return {"status": "ok"}
