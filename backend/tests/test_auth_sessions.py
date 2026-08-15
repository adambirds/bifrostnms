from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import Request, Response

from bifrostnms.auth.security import create_session, delete_session


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
async def test_create_session_persists_to_redis_and_sets_cookie():
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
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
async def test_delete_session_removes_redis_key_and_cookie():
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
