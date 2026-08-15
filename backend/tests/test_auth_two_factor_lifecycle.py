from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from bifrostnms.auth.two_factor import (
    RECOVERY_CODE_COUNT,
    consume_login_challenge,
    create_login_challenge,
    create_totp_setup,
    encrypt_secret,
    user_has_two_factor,
    verify_totp_setup,
    verify_two_factor,
)
from bifrostnms.models import AuthenticationChallenge, TwoFactorMethod, User


@pytest.mark.asyncio
async def test_recovery_code_rejects_unknown_code() -> None:
    queryset = MagicMock()
    queryset.first = AsyncMock(return_value=None)

    with patch("bifrostnms.auth.two_factor.RecoveryCode.filter", return_value=queryset):
        assert (
            await verify_two_factor(cast(User, SimpleNamespace()), "UNKNOWN-CODE", recovery=True)
            is False
        )


@pytest.mark.asyncio
async def test_create_totp_setup_replaces_unverified_method() -> None:
    user = cast(User, SimpleNamespace(email="user@example.com"))
    existing = MagicMock()
    existing.delete = AsyncMock()
    method = cast(TwoFactorMethod, SimpleNamespace())

    with (
        patch("bifrostnms.auth.two_factor.TwoFactorMethod.filter", return_value=existing),
        patch(
            "bifrostnms.auth.two_factor.TwoFactorMethod.create",
            new=AsyncMock(return_value=method),
        ) as create_mock,
        patch("bifrostnms.auth.two_factor.pyotp.random_base32", return_value="SECRET"),
    ):
        result_method, secret, uri = await create_totp_setup(user)

    existing.delete.assert_awaited_once()
    assert result_method is method
    assert secret == "SECRET"
    assert "user%40example.com" in uri
    assert create_mock.await_args is not None
    assert create_mock.await_args.kwargs["is_enabled"] is False


@pytest.mark.asyncio
async def test_verify_totp_setup_rejects_missing_method() -> None:
    queryset = MagicMock()
    queryset.first = AsyncMock(return_value=None)
    with (
        patch("bifrostnms.auth.two_factor.TwoFactorMethod.filter", return_value=queryset),
        pytest.raises(ValueError, match="TOTP setup not found"),
    ):
        await verify_totp_setup(cast(User, SimpleNamespace()), "missing", "123456")


@pytest.mark.asyncio
async def test_verify_totp_setup_rejects_invalid_code() -> None:
    method = SimpleNamespace(secret_encrypted=encrypt_secret("SECRET"))
    queryset = MagicMock()
    queryset.first = AsyncMock(return_value=method)
    verifier = MagicMock()
    verifier.verify.return_value = False
    with (
        patch("bifrostnms.auth.two_factor.TwoFactorMethod.filter", return_value=queryset),
        patch("bifrostnms.auth.two_factor.pyotp.TOTP", return_value=verifier),
        pytest.raises(ValueError, match="Invalid verification code"),
    ):
        await verify_totp_setup(cast(User, SimpleNamespace()), "method", "123456")


@pytest.mark.asyncio
async def test_verify_totp_setup_enables_method_and_creates_recovery_codes() -> None:
    user = cast(User, SimpleNamespace(id=uuid4(), _saved_in_db=True))
    method = SimpleNamespace(
        secret_encrypted=encrypt_secret("SECRET"),
        is_enabled=False,
        verified_at=None,
        save=AsyncMock(),
    )
    methods = MagicMock()
    methods.first = AsyncMock(return_value=method)
    recovery_codes = MagicMock()
    recovery_codes.delete = AsyncMock()
    recovery_model = MagicMock()
    recovery_model.filter.return_value = recovery_codes
    recovery_model.bulk_create = AsyncMock()
    recovery_model.side_effect = SimpleNamespace
    verifier = MagicMock()
    verifier.verify.return_value = True

    with (
        patch("bifrostnms.auth.two_factor.TwoFactorMethod.filter", return_value=methods),
        patch("bifrostnms.auth.two_factor.RecoveryCode", recovery_model),
        patch("bifrostnms.auth.two_factor.pyotp.TOTP", return_value=verifier),
        patch(
            "bifrostnms.auth.two_factor.generate_recovery_code",
            side_effect=[f"CODE-{index}" for index in range(RECOVERY_CODE_COUNT)],
        ),
    ):
        codes = await verify_totp_setup(user, "method", "123456")

    assert len(codes) == RECOVERY_CODE_COUNT
    assert method.is_enabled is True
    assert method.verified_at is not None
    method.save.assert_awaited_once_with(update_fields=["is_enabled", "verified_at"])
    recovery_codes.delete.assert_awaited_once()
    assert len(recovery_model.bulk_create.await_args.args[0]) == RECOVERY_CODE_COUNT


@pytest.mark.asyncio
async def test_user_has_two_factor_uses_enabled_method() -> None:
    queryset = MagicMock()
    queryset.exists = AsyncMock(return_value=True)
    with patch(
        "bifrostnms.auth.two_factor.TwoFactorMethod.filter", return_value=queryset
    ) as filter_mock:
        assert await user_has_two_factor(cast(User, SimpleNamespace())) is True

    assert filter_mock.call_args.kwargs["is_enabled"] is True


@pytest.mark.asyncio
async def test_create_login_challenge_replaces_pending_challenge() -> None:
    user = cast(User, SimpleNamespace())
    pending = MagicMock()
    pending.delete = AsyncMock()

    with (
        patch("bifrostnms.auth.two_factor.AuthenticationChallenge.filter", return_value=pending),
        patch(
            "bifrostnms.auth.two_factor.AuthenticationChallenge.create", new=AsyncMock()
        ) as create_mock,
        patch("bifrostnms.auth.two_factor.secrets.token_urlsafe", return_value="token"),
    ):
        assert await create_login_challenge(user) == "token"

    pending.delete.assert_awaited_once()
    assert create_mock.await_args is not None
    assert create_mock.await_args.kwargs["challenge_type"] == "two_factor_login"


@pytest.mark.asyncio
async def test_consume_login_challenge_rejects_expired_challenge() -> None:
    challenge = SimpleNamespace(
        expires_at=datetime.now(UTC) - timedelta(seconds=1), user=cast(User, SimpleNamespace())
    )
    queryset = MagicMock()
    queryset.select_related.return_value = queryset
    queryset.first = AsyncMock(return_value=challenge)

    with patch("bifrostnms.auth.two_factor.AuthenticationChallenge.filter", return_value=queryset):
        assert await consume_login_challenge("token") is None


@pytest.mark.asyncio
async def test_consume_login_challenge_marks_valid_challenge_used() -> None:
    user = cast(User, SimpleNamespace())
    challenge_save = AsyncMock()
    challenge = cast(
        AuthenticationChallenge,
        SimpleNamespace(
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
            user=user,
            consumed_at=None,
            save=challenge_save,
        ),
    )
    queryset = MagicMock()
    queryset.select_related.return_value = queryset
    queryset.first = AsyncMock(return_value=challenge)

    with patch("bifrostnms.auth.two_factor.AuthenticationChallenge.filter", return_value=queryset):
        assert await consume_login_challenge("token") is user

    assert challenge.consumed_at is not None
    challenge_save.assert_awaited_once_with(update_fields=["consumed_at"])
