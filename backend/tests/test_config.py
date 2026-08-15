from bifrostnms.config import Settings


def test_default_redis_databases_are_separated() -> None:
    settings = Settings.model_construct()

    assert settings.redis_url.endswith("/0")
    assert settings.celery_broker_url.endswith("/1")
    assert settings.celery_result_backend.endswith("/2")


def test_session_ttl_seconds() -> None:
    settings = Settings.model_construct(session_ttl_days=2)
    assert settings.session_ttl_seconds == 172800


def test_cors_origins_are_parsed_and_trimmed() -> None:
    settings = Settings.model_construct(
        cors_origins="http://localhost:3000, http://localhost:3001 , ,",
    )

    assert settings.cors_origin_list == ["http://localhost:3000", "http://localhost:3001"]
