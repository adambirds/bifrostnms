from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".devcontainer/.env"),
        env_prefix="BIFROSTNMS_",
        extra="ignore",
    )

    env: str = "development"
    database_url: str = "postgres://bifrostnms:bifrostnms@postgres:5432/bifrostnms"
    redis_url: str = "redis://redis:6379/0"
    auto_create_schema: bool = False

    # Celery deliberately uses separate Redis logical databases from browser
    # sessions so queue/result data cannot collide with session keys.
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"
    celery_task_always_eager: bool = False

    session_cookie_name: str = "bifrost_session"
    session_key_prefix: str = "bifrostnms:session:"
    session_ttl_days: int = 30
    cookie_secure: bool = False
    cookie_domain: str | None = None
    cors_origins: str = "http://localhost:3000,http://localhost:3001"

    # Development default only. Production deployments must provide a long random value.
    auth_encryption_key: str = "development-only-change-me"

    # WebAuthn relying-party configuration. Passkeys require a secure context in production.
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "BifrostNMS"
    webauthn_origin: str = "http://localhost:3001"

    # Provider-neutral email selection.
    email_backend: Literal["smtp", "microsoft_graph"] = "smtp"

    # SMTP email delivery. Authentication is optional: omit both username and password
    # for an unauthenticated SMTP relay.
    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_security: Literal["none", "starttls", "ssl"] = "none"
    smtp_timeout_seconds: float = 15.0
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "bifrostnms@localhost"
    smtp_from_name: str | None = "BifrostNMS"

    # Microsoft Graph app-only delivery using certificate credentials. Credentials can
    # be supplied either as base64-encoded PEM values or mounted PEM file paths.
    microsoft_graph_tenant_id: str | None = None
    microsoft_graph_client_id: str | None = None
    microsoft_graph_sender_email: str | None = None
    microsoft_graph_certificate_base64: str | None = None
    microsoft_graph_private_key_base64: str | None = None
    microsoft_graph_certificate_path: str | None = None
    microsoft_graph_private_key_path: str | None = None
    microsoft_graph_private_key_passphrase: str | None = None
    microsoft_graph_from_name: str | None = "BifrostNMS"
    microsoft_graph_timeout_seconds: float = 15.0

    @property
    def session_ttl_seconds(self) -> int:
        return self.session_ttl_days * 24 * 60 * 60

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
