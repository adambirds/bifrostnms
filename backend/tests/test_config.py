import pytest
from pydantic import ValidationError

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


def test_production_rejects_insecure_authentication_defaults() -> None:
    with pytest.raises(ValidationError, match="COOKIE_SECURE must be true"):
        Settings(env="production")


def test_production_accepts_explicit_secure_authentication_settings() -> None:
    settings = Settings(
        env="production",
        cookie_secure=True,
        auth_encryption_key="a" * 32,
        auth_frontend_url="https://auth.example.com",
        webauthn_origin="https://auth.example.com",
        webauthn_rp_id="auth.example.com",
        cors_origins="https://app.example.com,https://auth.example.com",
    )

    assert settings.env == "production"
