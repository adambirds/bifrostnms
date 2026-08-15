from datetime import UTC, datetime
from uuid import uuid4

from bifrostnms.auth.security import (
    SessionData,
    hash_password,
    hash_token,
    normalize_email,
    verify_password,
)


def test_normalize_email_trims_and_lowercases() -> None:
    assert normalize_email("  Adam.Birds@Example.COM  ") == "adam.birds@example.com"


def test_password_hash_round_trip() -> None:
    encoded = hash_password("correct horse battery staple")

    assert encoded != "correct horse battery staple"
    assert verify_password("correct horse battery staple", encoded) is True
    assert verify_password("wrong password", encoded) is False


def test_hash_token_is_deterministic_sha256() -> None:
    assert hash_token("token") == "3c469e9d6c5875d37a43f3535f567666c7e0137a68e21193c044b7c08acec5f"


def test_session_data_json_round_trip() -> None:
    now = datetime.now(UTC)
    user_id = uuid4()
    realm_id = uuid4()
    session = SessionData(
        user_id=user_id,
        active_realm_id=realm_id,
        auth_method="passkey",
        created_at=now,
        last_activity=now,
        user_agent="pytest",
        ip_address="127.0.0.1",
        redis_key="bifrostnms:session:test",
    )

    raw = session.to_json()
    restored = SessionData.from_json(raw, redis_key=session.redis_key)

    assert restored.user_id == user_id
    assert restored.active_realm_id == realm_id
    assert restored.auth_method == "passkey"
    assert restored.created_at == now
    assert restored.last_activity == now
    assert restored.user_agent == "pytest"
    assert restored.ip_address == "127.0.0.1"
    assert restored.redis_key == session.redis_key
    assert "redis_key" not in raw


def test_session_data_supports_no_active_realm() -> None:
    now = datetime.now(UTC)
    session = SessionData(
        user_id=uuid4(),
        active_realm_id=None,
        auth_method="password",
        created_at=now,
        last_activity=now,
        user_agent="",
        ip_address=None,
        redis_key="key",
    )

    restored = SessionData.from_json(session.to_json(), redis_key="key")
    assert restored.active_realm_id is None
    assert restored.ip_address is None
