from bifrostnms.config import Settings


def test_default_redis_databases_are_separated():
    settings = Settings(_env_file=None)

    assert settings.redis_url.endswith("/0")
    assert settings.celery_broker_url.endswith("/1")
    assert settings.celery_result_backend.endswith("/2")


def test_session_ttl_seconds():
    settings = Settings(_env_file=None, session_ttl_days=2)
    assert settings.session_ttl_seconds == 172800


def test_cors_origins_are_parsed_and_trimmed():
    settings = Settings(
        _env_file=None,
        cors_origins="http://localhost:3000, http://localhost:3001 ,,",
    )

    assert settings.cors_origin_list == ["http://localhost:3000", "http://localhost:3001"]
