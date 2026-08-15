from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from bifrostnms.auth.permissions import require_superuser


@pytest.mark.asyncio
async def test_require_superuser_allows_superuser():
    user = SimpleNamespace(is_superuser=True)
    session = object()

    with patch(
        "bifrostnms.auth.permissions.get_session_user",
        new=AsyncMock(return_value=(user, session)),
    ):
        result = await require_superuser(object())

    assert result == (user, session)


@pytest.mark.asyncio
async def test_require_superuser_rejects_normal_user():
    user = SimpleNamespace(is_superuser=False)

    with patch(
        "bifrostnms.auth.permissions.get_session_user",
        new=AsyncMock(return_value=(user, object())),
    ):
        with pytest.raises(HTTPException) as exc:
            await require_superuser(object())

    assert exc.value.status_code == 403
    assert exc.value.detail == "Installation superuser access required"
