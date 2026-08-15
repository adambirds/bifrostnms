from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Request, Response

from bifrostnms.api.two_factor import (
    disable_totp,
    setup_totp,
    two_factor_enabled,
    verify_login_challenge,
    verify_totp,
)
from bifrostnms.api.webauthn import (
    authenticate_options,
    authenticate_verify,
    delete_passkey,
    register_options,
    register_verify,
)
from bifrostnms.auth.security import SessionData
from bifrostnms.models import User
from bifrostnms.schemas.auth import (
    TotpSetupVerifyRequest,
    TwoFactorVerifyRequest,
    UserResponse,
    WebAuthnAuthenticationVerifyRequest,
    WebAuthnRegistrationVerifyRequest,
)


def request() -> Request:
    return cast(Request, SimpleNamespace())


def user(*, is_active: bool = True) -> User:
    return cast(User, SimpleNamespace(id=uuid4(), is_active=is_active))


def user_response(user_id: UUID) -> UserResponse:
    return UserResponse(
        id=user_id,
        email="user@example.com",
        first_name="Test",
        last_name="User",
        full_name="Test User",
        email_verified=False,
        is_superuser=False,
        active_realm_id=None,
        realms=[],
    )


@pytest.mark.asyncio
async def test_login_challenge_rejects_expired_challenge() -> None:
    payload = TwoFactorVerifyRequest(challenge_token="expired", code="123456")

    with (
        patch(
            "bifrostnms.api.two_factor.consume_login_challenge",
            new=AsyncMock(return_value=None),
        ),
        pytest.raises(HTTPException, match="2FA challenge expired") as exc,
    ):
        await verify_login_challenge(payload, request(), Response())

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_login_challenge_rejects_invalid_code() -> None:
    account = user()
    payload = TwoFactorVerifyRequest(challenge_token="challenge", code="123456")

    with (
        patch(
            "bifrostnms.api.two_factor.consume_login_challenge",
            new=AsyncMock(return_value=account),
        ),
        patch("bifrostnms.api.two_factor.verify_two_factor", new=AsyncMock(return_value=False)),
        pytest.raises(HTTPException, match="Invalid verification code") as exc,
    ):
        await verify_login_challenge(payload, request(), Response())

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_login_challenge_creates_two_factor_session() -> None:
    account = user()
    session = cast(SessionData, SimpleNamespace())
    serialized = user_response(account.id)
    payload = TwoFactorVerifyRequest(
        challenge_token="challenge", code="recovery-code", recovery_code=True
    )

    with (
        patch(
            "bifrostnms.api.two_factor.consume_login_challenge",
            new=AsyncMock(return_value=account),
        ),
        patch(
            "bifrostnms.api.two_factor.verify_two_factor", new=AsyncMock(return_value=True)
        ) as verify_mock,
        patch(
            "bifrostnms.api.two_factor.create_session", new=AsyncMock(return_value=session)
        ) as session_mock,
        patch("bifrostnms.api.two_factor.serialize_user", new=AsyncMock(return_value=serialized)),
    ):
        result = await verify_login_challenge(payload, request(), Response())

    assert result.user == serialized
    verify_mock.assert_awaited_once_with(account, "recovery-code", recovery=True)
    assert session_mock.await_args is not None
    assert session_mock.await_args.kwargs["auth_method"] == "password+2fa"


@pytest.mark.asyncio
async def test_setup_totp_returns_provisioning_details() -> None:
    account = user()
    method_id = uuid4()
    method = SimpleNamespace(id=method_id)

    with (
        patch(
            "bifrostnms.api.two_factor.get_session_user",
            new=AsyncMock(return_value=(account, SimpleNamespace())),
        ),
        patch(
            "bifrostnms.api.two_factor.create_totp_setup",
            new=AsyncMock(return_value=(method, "secret", "otpauth://totp/example")),
        ),
    ):
        result = await setup_totp(request())

    assert result.method_id == method_id
    assert result.secret == "secret"
    assert result.provisioning_uri == "otpauth://totp/example"


@pytest.mark.asyncio
async def test_verify_totp_returns_recovery_codes() -> None:
    account = user()
    method_id = uuid4()
    payload = TotpSetupVerifyRequest(method_id=method_id, code="123456")

    with (
        patch(
            "bifrostnms.api.two_factor.get_session_user",
            new=AsyncMock(return_value=(account, SimpleNamespace())),
        ),
        patch(
            "bifrostnms.api.two_factor.verify_totp_setup",
            new=AsyncMock(return_value=["AAAA-BBBB-CCCC"]),
        ) as verify_mock,
    ):
        result = await verify_totp(payload, request())

    assert result.recovery_codes == ["AAAA-BBBB-CCCC"]
    verify_mock.assert_awaited_once_with(account, str(method_id), "123456")


@pytest.mark.asyncio
async def test_verify_totp_converts_validation_error_to_bad_request() -> None:
    payload = TotpSetupVerifyRequest(method_id=uuid4(), code="123456")

    with (
        patch(
            "bifrostnms.api.two_factor.get_session_user",
            new=AsyncMock(return_value=(user(), SimpleNamespace())),
        ),
        patch(
            "bifrostnms.api.two_factor.verify_totp_setup",
            new=AsyncMock(side_effect=ValueError("Invalid setup code")),
        ),
        pytest.raises(HTTPException, match="Invalid setup code") as exc,
    ):
        await verify_totp(payload, request())

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_disable_totp_deletes_method_and_recovery_codes() -> None:
    account = user()
    methods = MagicMock()
    methods.delete = AsyncMock()
    recovery_codes = MagicMock()
    recovery_codes.delete = AsyncMock()

    with (
        patch(
            "bifrostnms.api.two_factor.get_session_user",
            new=AsyncMock(return_value=(account, SimpleNamespace())),
        ),
        patch("bifrostnms.api.two_factor.TwoFactorMethod.filter", return_value=methods),
        patch("bifrostnms.api.two_factor.RecoveryCode.filter", return_value=recovery_codes),
    ):
        await disable_totp(request())

    methods.delete.assert_awaited_once()
    recovery_codes.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_two_factor_enabled_returns_status() -> None:
    account = user()
    with (
        patch(
            "bifrostnms.api.two_factor.get_session_user",
            new=AsyncMock(return_value=(account, SimpleNamespace())),
        ),
        patch(
            "bifrostnms.api.two_factor.user_has_two_factor",
            new=AsyncMock(return_value=True),
        ),
    ):
        assert await two_factor_enabled(request()) == {"enabled": True}


@pytest.mark.asyncio
async def test_passkey_registration_options_are_wrapped() -> None:
    account = user()
    options = {"challenge_id": uuid4(), "options": {"challenge": "encoded"}}

    with (
        patch(
            "bifrostnms.api.webauthn.get_session_user",
            new=AsyncMock(return_value=(account, SimpleNamespace())),
        ),
        patch(
            "bifrostnms.api.webauthn.registration_options",
            new=AsyncMock(return_value=options),
        ),
    ):
        result = await register_options(request())

    assert result.challenge_id == options["challenge_id"]
    assert result.options == options["options"]


@pytest.mark.asyncio
async def test_passkey_registration_returns_created_credential() -> None:
    account = user()
    credential_id = uuid4()
    payload = WebAuthnRegistrationVerifyRequest(
        challenge_id=uuid4(), credential={"id": "browser-id"}, name="Laptop"
    )
    credential = SimpleNamespace(id=credential_id, name="Laptop")

    with (
        patch(
            "bifrostnms.api.webauthn.get_session_user",
            new=AsyncMock(return_value=(account, SimpleNamespace())),
        ),
        patch(
            "bifrostnms.api.webauthn.verify_registration",
            new=AsyncMock(return_value=credential),
        ),
    ):
        result = await register_verify(payload, request())

    assert result == {"id": str(credential_id), "name": "Laptop"}


@pytest.mark.asyncio
async def test_passkey_registration_rejects_invalid_credential() -> None:
    payload = WebAuthnRegistrationVerifyRequest(challenge_id=uuid4(), credential={}, name="Laptop")
    with (
        patch(
            "bifrostnms.api.webauthn.get_session_user",
            new=AsyncMock(return_value=(user(), SimpleNamespace())),
        ),
        patch(
            "bifrostnms.api.webauthn.verify_registration",
            new=AsyncMock(side_effect=ValueError("Invalid credential")),
        ),
        pytest.raises(HTTPException, match="Invalid credential") as exc,
    ):
        await register_verify(payload, request())

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_passkey_authentication_options_are_wrapped() -> None:
    options = {"challenge_id": uuid4(), "options": {"challenge": "encoded"}}
    with patch(
        "bifrostnms.api.webauthn.authentication_options",
        new=AsyncMock(return_value=options),
    ):
        result = await authenticate_options()

    assert result.challenge_id == options["challenge_id"]
    assert result.options == options["options"]


@pytest.mark.asyncio
async def test_passkey_authentication_rejects_invalid_credential() -> None:
    payload = WebAuthnAuthenticationVerifyRequest(challenge_id=uuid4(), credential={})
    with (
        patch(
            "bifrostnms.api.webauthn.verify_authentication",
            new=AsyncMock(side_effect=ValueError("Invalid passkey")),
        ),
        pytest.raises(HTTPException, match="Invalid passkey") as exc,
    ):
        await authenticate_verify(payload, request(), Response())

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_passkey_authentication_rejects_disabled_account() -> None:
    payload = WebAuthnAuthenticationVerifyRequest(challenge_id=uuid4(), credential={})
    with (
        patch(
            "bifrostnms.api.webauthn.verify_authentication",
            new=AsyncMock(return_value=user(is_active=False)),
        ),
        pytest.raises(HTTPException, match="Account is disabled") as exc,
    ):
        await authenticate_verify(payload, request(), Response())

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_passkey_authentication_creates_session() -> None:
    account = user()
    session = cast(SessionData, SimpleNamespace())
    serialized = user_response(account.id)
    payload = WebAuthnAuthenticationVerifyRequest(challenge_id=uuid4(), credential={})

    with (
        patch(
            "bifrostnms.api.webauthn.verify_authentication",
            new=AsyncMock(return_value=account),
        ),
        patch(
            "bifrostnms.api.webauthn.create_session", new=AsyncMock(return_value=session)
        ) as session_mock,
        patch("bifrostnms.api.webauthn.serialize_user", new=AsyncMock(return_value=serialized)),
    ):
        result = await authenticate_verify(payload, request(), Response())

    assert result.user == serialized
    assert session_mock.await_args is not None
    assert session_mock.await_args.kwargs["auth_method"] == "passkey"


@pytest.mark.asyncio
async def test_delete_passkey_rejects_unknown_credential() -> None:
    queryset = MagicMock()
    queryset.delete = AsyncMock(return_value=0)
    with (
        patch(
            "bifrostnms.api.webauthn.get_session_user",
            new=AsyncMock(return_value=(user(), SimpleNamespace())),
        ),
        patch("bifrostnms.api.webauthn.WebAuthnCredential.filter", return_value=queryset),
        pytest.raises(HTTPException, match="Passkey not found") as exc,
    ):
        await delete_passkey("missing", request())

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_passkey_removes_owned_credential() -> None:
    queryset = MagicMock()
    queryset.delete = AsyncMock(return_value=1)
    with (
        patch(
            "bifrostnms.api.webauthn.get_session_user",
            new=AsyncMock(return_value=(user(), SimpleNamespace())),
        ),
        patch("bifrostnms.api.webauthn.WebAuthnCredential.filter", return_value=queryset),
    ):
        await delete_passkey("credential", request())

    queryset.delete.assert_awaited_once()
