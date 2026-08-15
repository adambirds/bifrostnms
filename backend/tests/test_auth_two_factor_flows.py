from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pyotp
import pytest

from bifrostnms.auth.two_factor import encrypt_secret, hash_recovery_code, verify_two_factor
from bifrostnms.models import User


@pytest.mark.asyncio
async def test_verify_totp_updates_last_used_timestamp() -> None:
    secret = pyotp.random_base32()
    method = SimpleNamespace(
        secret_encrypted=encrypt_secret(secret),
        last_used_at=None,
        save=AsyncMock(),
    )
    queryset = MagicMock()
    queryset.first = AsyncMock(return_value=method)
    user = cast(User, SimpleNamespace())

    with patch("bifrostnms.auth.two_factor.TwoFactorMethod.filter", return_value=queryset):
        valid = await verify_two_factor(user, pyotp.TOTP(secret).now())

    assert valid is True
    assert method.last_used_at is not None
    method.save.assert_awaited_once_with(update_fields=["last_used_at"])


@pytest.mark.asyncio
async def test_verify_totp_rejects_when_no_enabled_method_exists() -> None:
    queryset = MagicMock()
    queryset.first = AsyncMock(return_value=None)
    user = cast(User, SimpleNamespace())

    with patch("bifrostnms.auth.two_factor.TwoFactorMethod.filter", return_value=queryset):
        assert await verify_two_factor(user, "123456") is False


@pytest.mark.asyncio
async def test_recovery_code_is_single_use() -> None:
    recovery = SimpleNamespace(used_at=None, save=AsyncMock())
    queryset = MagicMock()
    queryset.first = AsyncMock(return_value=recovery)
    user = cast(User, SimpleNamespace())

    with patch(
        "bifrostnms.auth.two_factor.RecoveryCode.filter", return_value=queryset
    ) as filter_mock:
        valid = await verify_two_factor(user, "ABCD-EFGH-JKLM", recovery=True)

    assert valid is True
    assert recovery.used_at is not None
    recovery.save.assert_awaited_once_with(update_fields=["used_at"])
    filter_mock.assert_called_once_with(
        user=user,
        code_hash=hash_recovery_code("ABCD-EFGH-JKLM"),
        used_at=None,
    )
