from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bifrostnms.auth import redis as redis_module


def test_get_redis_lazily_creates_single_client() -> None:
    client = object()
    redis_module._client = None
    settings = SimpleNamespace(redis_url="redis://example/0")

    with (
        patch("bifrostnms.auth.redis.get_settings", return_value=settings),
        patch("bifrostnms.auth.redis.Redis.from_url", return_value=client) as from_url,
    ):
        assert redis_module.get_redis() is client
        assert redis_module.get_redis() is client

    from_url.assert_called_once_with("redis://example/0", decode_responses=True)
    redis_module._client = None


@pytest.mark.asyncio
async def test_close_redis_closes_and_clears_client() -> None:
    client = AsyncMock()
    redis_module._client = client

    await redis_module.close_redis()

    client.aclose.assert_awaited_once()
    assert redis_module._client is None
