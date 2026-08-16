from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bifrostnms.auth.account_lifecycle import (
    consume_account_token,
    create_account_token,
    reset_password,
    verify_email_token,
)
from bifrostnms.models import User


def account(**overrides: object) -> User:
    values = {
        "email_verified": False,
        "is_active": True,
        "password_hash": "old-hash",
        "session_version": 1,
        "save": AsyncMock(),
    }
    values.update(overrides)
    return cast(User, SimpleNamespace(**values))


@pytest.mark.asyncio
async def test_create_account_token_consumes_older_token_and_hashes_new_token() -> None:
    user = account()
    challenges = MagicMock()
    challenges.update = AsyncMock()
    with (
        patch(
            "bifrostnms.auth.account_lifecycle.AuthenticationChallenge.filter",
            return_value=challenges,
        ),
        patch(
            "bifrostnms.auth.account_lifecycle.AuthenticationChallenge.create", new=AsyncMock()
        ) as create,
        patch("bifrostnms.auth.account_lifecycle.secrets.token_urlsafe", return_value="raw-token"),
    ):
        token = await create_account_token(user, "password_reset", timedelta(minutes=30))

    assert token == "raw-token"
    challenges.update.assert_awaited_once()
    assert create.await_args is not None
    assert create.await_args.kwargs["challenge_hash"] != token


@pytest.mark.asyncio
async def test_consume_account_token_marks_valid_challenge_consumed() -> None:
    user = account()
    challenge = SimpleNamespace(user=user, consumed_at=None, save=AsyncMock())
    challenges = MagicMock()
    challenges.select_related.return_value = challenges
    challenges.first = AsyncMock(return_value=challenge)
    with patch(
        "bifrostnms.auth.account_lifecycle.AuthenticationChallenge.filter",
        return_value=challenges,
    ):
        result = await consume_account_token("token", "email_verification")

    assert result is user
    assert isinstance(challenge.consumed_at, datetime)
    challenge.save.assert_awaited_once_with(update_fields=["consumed_at"])


@pytest.mark.asyncio
async def test_verify_email_token_updates_user() -> None:
    save = AsyncMock()
    user = account(save=save)
    with patch(
        "bifrostnms.auth.account_lifecycle.consume_account_token",
        new=AsyncMock(return_value=user),
    ):
        assert await verify_email_token("token") is user

    assert user.email_verified is True
    save.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_password_changes_hash_and_invalidates_sessions() -> None:
    save = AsyncMock()
    user = account(save=save)
    with (
        patch(
            "bifrostnms.auth.account_lifecycle.consume_account_token",
            new=AsyncMock(return_value=user),
        ),
        patch("bifrostnms.auth.account_lifecycle.hash_password", return_value="new-hash"),
    ):
        assert await reset_password("token", "new-password-value") is user

    assert user.password_hash == "new-hash"
    assert user.session_version == 2
    save.assert_awaited_once()
