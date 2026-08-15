from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, Request

from bifrostnms.auth.permissions import require_superuser
from bifrostnms.auth.security import SessionData
from bifrostnms.models import User


@pytest.mark.asyncio
async def test_require_superuser_allows_superuser() -> None:
    user = cast(User, SimpleNamespace(is_superuser=True))
    session = cast(SessionData, object())
    request = cast(Request, object())

    with patch(
        "bifrostnms.auth.permissions.get_session_user",
        new=AsyncMock(return_value=(user, session)),
    ):
        result = await require_superuser(request)

    assert result == (user, session)


@pytest.mark.asyncio
async def test_require_superuser_rejects_normal_user() -> None:
    user = cast(User, SimpleNamespace(is_superuser=False))
    session = cast(SessionData, object())
    request = cast(Request, object())

    with patch(
        "bifrostnms.auth.permissions.get_session_user",
        new=AsyncMock(return_value=(user, session)),
    ):
        with pytest.raises(HTTPException) as exc:
            await require_superuser(request)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Installation superuser access required"
