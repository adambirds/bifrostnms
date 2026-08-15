from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from bifrostnms.auth.webauthn import _b64, verify_authentication, verify_registration


@pytest.mark.asyncio
async def test_verify_registration_stores_credential_and_consumes_challenge():
    user = SimpleNamespace(id=uuid4())
    challenge = SimpleNamespace(
        user_id=user.id,
        metadata={"challenge": _b64(b"challenge")},
        consumed_at=None,
        save=AsyncMock(),
    )
    stored = SimpleNamespace(id=uuid4())
    verification = SimpleNamespace(
        credential_id=b"credential-id",
        credential_public_key=b"public-key",
        sign_count=3,
        credential_device_type="single_device",
        credential_backed_up=False,
    )

    with (
        patch("bifrostnms.auth.webauthn._get_challenge", new=AsyncMock(return_value=challenge)),
        patch("bifrostnms.auth.webauthn.verify_registration_response", return_value=verification),
        patch(
            "bifrostnms.auth.webauthn.WebAuthnCredential.create",
            new=AsyncMock(return_value=stored),
        ) as create_mock,
    ):
        result = await verify_registration(
            user,
            "challenge-id",
            {"id": "browser-id", "response": {"transports": ["internal"]}},
            "Mac passkey",
        )

    assert result is stored
    assert create_mock.await_args.kwargs["credential_id"] == _b64(b"credential-id")
    assert create_mock.await_args.kwargs["public_key"] == _b64(b"public-key")
    assert create_mock.await_args.kwargs["name"] == "Mac passkey"
    assert create_mock.await_args.kwargs["transports"] == ["internal"]
    assert challenge.consumed_at is not None
    challenge.save.assert_awaited_once_with(update_fields=["consumed_at"])


@pytest.mark.asyncio
async def test_verify_registration_rejects_challenge_for_another_user():
    user = SimpleNamespace(id=uuid4())
    challenge = SimpleNamespace(user_id=uuid4())

    with patch(
        "bifrostnms.auth.webauthn._get_challenge",
        new=AsyncMock(return_value=challenge),
    ):
        with pytest.raises(ValueError, match="does not belong to this user"):
            await verify_registration(user, "challenge-id", {}, "Passkey")


@pytest.mark.asyncio
async def test_verify_authentication_updates_counter_and_consumes_challenge():
    user = SimpleNamespace(id=uuid4())
    challenge = SimpleNamespace(
        metadata={"challenge": _b64(b"challenge")},
        consumed_at=None,
        save=AsyncMock(),
    )
    stored = SimpleNamespace(
        public_key=_b64(b"public-key"),
        sign_count=4,
        user=user,
        last_used_at=None,
        device_type="",
        backed_up=False,
        save=AsyncMock(),
    )
    queryset = MagicMock()
    queryset.select_related.return_value = queryset
    queryset.first = AsyncMock(return_value=stored)
    verification = SimpleNamespace(
        new_sign_count=5,
        credential_device_type="multi_device",
        credential_backed_up=True,
    )

    with (
        patch("bifrostnms.auth.webauthn._get_challenge", new=AsyncMock(return_value=challenge)),
        patch("bifrostnms.auth.webauthn.WebAuthnCredential.filter", return_value=queryset),
        patch("bifrostnms.auth.webauthn.verify_authentication_response", return_value=verification),
    ):
        result = await verify_authentication("challenge-id", {"id": "credential-id"})

    assert result is user
    assert stored.sign_count == 5
    assert stored.last_used_at is not None
    assert stored.device_type == "multi_device"
    assert stored.backed_up is True
    stored.save.assert_awaited_once()
    assert challenge.consumed_at is not None
    challenge.save.assert_awaited_once_with(update_fields=["consumed_at"])
