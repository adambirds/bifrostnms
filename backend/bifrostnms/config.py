from functools import lru_cache

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

    @property
    def session_ttl_seconds(self) -> int:
        return self.session_ttl_days * 24 * 60 * 60

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
