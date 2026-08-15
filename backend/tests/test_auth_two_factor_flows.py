from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pyotp
import pytest

from bifrostnms.auth.two_factor import encrypt_secret, hash_recovery_code, verify_two_factor


@pytest.mark.asyncio
async def test_verify_totp_updates_last_used_timestamp():
    secret = pyotp.random_base32()
    method = SimpleNamespace(
        secret_encrypted=encrypt_secret(secret),
        last_used_at=None,
        save=AsyncMock(),
    )
    queryset = MagicMock()
    queryset.first = AsyncMock(return_value=method)

    with patch("bifrostnms.auth.two_factor.TwoFactorMethod.filter", return_value=queryset):
        valid = await verify_two_factor(SimpleNamespace(), pyotp.TOTP(secret).now())

    assert valid is True
    assert method.last_used_at is not None
    method.save.assert_awaited_once_with(update_fields=["last_used_at"])


@pytest.mark.asyncio
async def test_verify_totp_rejects_when_no_enabled_method_exists():
    queryset = MagicMock()
    queryset.first = AsyncMock(return_value=None)

    with patch("bifrostnms.auth.two_factor.TwoFactorMethod.filter", return_value=queryset):
        assert await verify_two_factor(SimpleNamespace(), "123456") is False


@pytest.mark.asyncio
async def test_recovery_code_is_single_use():
    recovery = SimpleNamespace(used_at=None, save=AsyncMock())
    queryset = MagicMock()
    queryset.first = AsyncMock(return_value=recovery)
    user = SimpleNamespace()

    with patch("bifrostnms.auth.two_factor.RecoveryCode.filter", return_value=queryset) as filter_mock:
        valid = await verify_two_factor(user, "ABCD-EFGH-JKLM", recovery=True)

    assert valid is True
    assert recovery.used_at is not None
    recovery.save.assert_awaited_once_with(update_fields=["used_at"])
    filter_mock.assert_called_once_with(
        user=user,
        code_hash=hash_recovery_code("ABCD-EFGH-JKLM"),
        used_at=None,
    )
