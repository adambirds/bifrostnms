from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request, Response

from bifrostnms.auth.security import (
    SessionData,
    _initial_realm_id,
    create_session,
    delete_session,
    get_session_user,
    set_active_realm,
)
from bifrostnms.models import User


def make_request(*, cookie: str | None = None) -> Request:
    headers = [(b"user-agent", b"pytest")]
    if cookie:
        headers.append((b"cookie", f"bifrost_session={cookie}".encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


@pytest.mark.asyncio
async def test_create_session_persists_to_redis_and_sets_cookie() -> None:
    user = cast(User, SimpleNamespace(id=uuid4(), is_superuser=False, session_version=1))
    realm_id = uuid4()
    redis = AsyncMock()
    settings = SimpleNamespace(
        session_key_prefix="bifrostnms:session:",
        session_ttl_seconds=3600,
        session_cookie_name="bifrost_session",
        cookie_secure=False,
        cookie_domain=None,
    )
    response = Response()

    with (
        patch("bifrostnms.auth.security.get_settings", return_value=settings),
        patch("bifrostnms.auth.security.get_redis", return_value=redis),
        patch("bifrostnms.auth.security._initial_realm_id", new=AsyncMock(return_value=realm_id)),
        patch("bifrostnms.auth.security.secrets.token_urlsafe", return_value="session-token"),
    ):
        session = await create_session(user, make_request(), response, auth_method="passkey")

    assert session.user_id == user.id
    assert session.active_realm_id == realm_id
    assert session.auth_method == "passkey"
    assert session.user_agent == "pytest"
    assert session.ip_address == "127.0.0.1"
    redis.set.assert_awaited_once()
    assert redis.set.await_args.kwargs["ex"] == 3600
    assert "bifrost_session=session-token" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_delete_session_removes_redis_key_and_cookie() -> None:
    redis = AsyncMock()
    settings = SimpleNamespace(
        session_key_prefix="bifrostnms:session:",
        session_cookie_name="bifrost_session",
        cookie_domain=None,
    )
    response = Response()

    with (
        patch("bifrostnms.auth.security.get_settings", return_value=settings),
        patch("bifrostnms.auth.security.get_redis", return_value=redis),
    ):
        await delete_session(make_request(cookie="session-token"), response)

    redis.delete.assert_awaited_once()
    deleted_key = redis.delete.await_args.args[0]
    assert deleted_key.startswith("bifrostnms:session:")
    assert "bifrost_session=" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_initial_realm_prefers_membership() -> None:
    user = cast(User, SimpleNamespace(is_superuser=True))
    realm_id = uuid4()
    membership = SimpleNamespace(realm=SimpleNamespace(id=realm_id))
    memberships = MagicMock()
    memberships.select_related.return_value = memberships
    memberships.first = AsyncMock(return_value=membership)

    with patch("bifrostnms.auth.security.RealmMembership.filter", return_value=memberships):
        assert await _initial_realm_id(user) == realm_id


@pytest.mark.asyncio
async def test_initial_realm_uses_first_active_realm_for_superuser() -> None:
    user = cast(User, SimpleNamespace(is_superuser=True))
    realm_id = uuid4()
    memberships = MagicMock()
    memberships.select_related.return_value = memberships
    memberships.first = AsyncMock(return_value=None)
    realms = MagicMock()
    realms.order_by.return_value = realms
    realms.first = AsyncMock(return_value=SimpleNamespace(id=realm_id))

    with (
        patch("bifrostnms.auth.security.RealmMembership.filter", return_value=memberships),
        patch("bifrostnms.auth.security.Realm.filter", return_value=realms),
    ):
        assert await _initial_realm_id(user) == realm_id


@pytest.mark.asyncio
async def test_get_session_user_requires_cookie() -> None:
    settings = SimpleNamespace(session_cookie_name="bifrost_session")
    with (
        patch("bifrostnms.auth.security.get_settings", return_value=settings),
        pytest.raises(HTTPException, match="Not authenticated") as exc,
    ):
        await get_session_user(make_request())

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_session_user_rejects_missing_redis_session() -> None:
    redis = AsyncMock()
    redis.get.return_value = None
    settings = SimpleNamespace(
        session_cookie_name="bifrost_session", session_key_prefix="bifrostnms:session:"
    )
    with (
        patch("bifrostnms.auth.security.get_settings", return_value=settings),
        patch("bifrostnms.auth.security.get_redis", return_value=redis),
        pytest.raises(HTTPException, match="Session expired") as exc,
    ):
        await get_session_user(make_request(cookie="token"))

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_session_user_deletes_session_for_missing_user() -> None:
    stored = SessionData(
        user_id=uuid4(),
        active_realm_id=None,
        auth_method="password",
        created_at=datetime.now(UTC),
        last_activity=datetime.now(UTC),
        user_agent="pytest",
        ip_address=None,
        redis_key="unused",
    )
    redis = AsyncMock()
    redis.get.return_value = stored.to_json()
    users = MagicMock()
    users.first = AsyncMock(return_value=None)
    settings = SimpleNamespace(
        session_cookie_name="bifrost_session", session_key_prefix="bifrostnms:session:"
    )
    with (
        patch("bifrostnms.auth.security.get_settings", return_value=settings),
        patch("bifrostnms.auth.security.get_redis", return_value=redis),
        patch("bifrostnms.auth.security.User.filter", return_value=users),
        pytest.raises(HTTPException, match="Session expired"),
    ):
        await get_session_user(make_request(cookie="token"))

    redis.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_session_user_refreshes_valid_session() -> None:
    user = cast(User, SimpleNamespace(id=uuid4(), session_version=1))
    stored = SessionData(
        user_id=user.id,
        active_realm_id=None,
        auth_method="password",
        created_at=datetime.now(UTC),
        last_activity=datetime.now(UTC),
        user_agent="pytest",
        ip_address=None,
        redis_key="unused",
    )
    redis = AsyncMock()
    redis.get.return_value = stored.to_json()
    users = MagicMock()
    users.first = AsyncMock(return_value=user)
    settings = SimpleNamespace(
        session_cookie_name="bifrost_session",
        session_key_prefix="bifrostnms:session:",
        session_ttl_seconds=3600,
    )
    with (
        patch("bifrostnms.auth.security.get_settings", return_value=settings),
        patch("bifrostnms.auth.security.get_redis", return_value=redis),
        patch("bifrostnms.auth.security.User.filter", return_value=users),
    ):
        result_user, result_session = await get_session_user(make_request(cookie="token"))

    assert result_user is user
    assert result_session.user_id == user.id
    redis.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_session_user_rejects_old_session_version() -> None:
    user = cast(User, SimpleNamespace(id=uuid4(), session_version=2))
    stored = SessionData(
        user_id=user.id,
        active_realm_id=None,
        auth_method="password",
        created_at=datetime.now(UTC),
        last_activity=datetime.now(UTC),
        user_agent="pytest",
        ip_address=None,
        redis_key="unused",
        user_session_version=1,
    )
    redis = AsyncMock()
    redis.get.return_value = stored.to_json()
    users = MagicMock()
    users.first = AsyncMock(return_value=user)
    settings = SimpleNamespace(
        session_cookie_name="bifrost_session", session_key_prefix="bifrostnms:session:"
    )
    with (
        patch("bifrostnms.auth.security.get_settings", return_value=settings),
        patch("bifrostnms.auth.security.get_redis", return_value=redis),
        patch("bifrostnms.auth.security.User.filter", return_value=users),
        pytest.raises(HTTPException, match="Session expired"),
    ):
        await get_session_user(make_request(cookie="token"))

    redis.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_active_realm_updates_redis_session() -> None:
    realm_id = uuid4()
    stored = SessionData(
        user_id=uuid4(),
        active_realm_id=None,
        auth_method="password",
        created_at=datetime.now(UTC),
        last_activity=datetime.now(UTC),
        user_agent="pytest",
        ip_address=None,
        redis_key="session-key",
    )
    redis = AsyncMock()
    settings = SimpleNamespace(session_ttl_seconds=3600)
    with (
        patch("bifrostnms.auth.security.get_settings", return_value=settings),
        patch("bifrostnms.auth.security.get_redis", return_value=redis),
    ):
        await set_active_realm(stored, realm_id)

    assert stored.active_realm_id == realm_id
    redis.set.assert_awaited_once()
