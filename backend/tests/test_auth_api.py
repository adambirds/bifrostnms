from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Request, Response

from bifrostnms.api.auth import (
    activate_realm,
    confirm_email_verification,
    confirm_password_reset,
    forgot_password,
    login,
    logout,
    me,
    request_email_verification,
    serialize_user,
    signup,
)
from bifrostnms.api.security import security_summary
from bifrostnms.auth.security import SessionData
from bifrostnms.models import Realm, User
from bifrostnms.schemas.auth import (
    EmailRequest,
    LoginRequest,
    PasswordResetRequest,
    SignupRequest,
    TokenRequest,
    UserResponse,
)


def request() -> Request:
    return cast(Request, SimpleNamespace())


def account(*, is_active: bool = True, is_superuser: bool = False) -> User:
    return cast(
        User,
        SimpleNamespace(
            id=uuid4(),
            email="user@example.com",
            password_hash="hash",
            first_name="Test",
            last_name="User",
            full_name="Test User",
            email_verified=False,
            is_active=is_active,
            is_superuser=is_superuser,
            session_version=1,
        ),
    )


def session(*, active_realm_id: UUID | None = None) -> SessionData:
    return cast(SessionData, SimpleNamespace(active_realm_id=active_realm_id))


def serialized_user(user_id: UUID) -> UserResponse:
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


def queryset_with_first(value: object) -> MagicMock:
    queryset = MagicMock()
    queryset.first = AsyncMock(return_value=value)
    queryset.select_related.return_value = queryset
    return queryset


@pytest.mark.asyncio
async def test_request_email_verification_sends_token_for_unverified_user() -> None:
    user = account()
    with (
        patch(
            "bifrostnms.api.auth.get_session_user",
            new=AsyncMock(return_value=(user, session())),
        ),
        patch(
            "bifrostnms.api.auth.create_verification_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("bifrostnms.api.auth._send_account_email") as email_mock,
    ):
        result = await request_email_verification(request())

    assert result == {"detail": "Verification email requested"}
    assert email_mock.call_args.kwargs["token"] == "token"


@pytest.mark.asyncio
async def test_confirm_email_verification_rejects_invalid_token() -> None:
    with (
        patch("bifrostnms.api.auth.verify_email_token", new=AsyncMock(return_value=None)),
        pytest.raises(HTTPException, match="Invalid or expired token") as exc,
    ):
        await confirm_email_verification(TokenRequest(token="x" * 32))

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_forgot_password_does_not_reveal_missing_account() -> None:
    with patch("bifrostnms.api.auth.User.filter", return_value=queryset_with_first(None)):
        result = await forgot_password(EmailRequest(email="missing@example.com"))

    assert result == {"detail": "If the account exists, a reset email has been sent"}


@pytest.mark.asyncio
async def test_forgot_password_sends_token_for_active_account() -> None:
    user = account()
    with (
        patch("bifrostnms.api.auth.User.filter", return_value=queryset_with_first(user)),
        patch(
            "bifrostnms.api.auth.create_password_reset_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("bifrostnms.api.auth._send_account_email") as email_mock,
    ):
        await forgot_password(EmailRequest(email="USER@example.com"))

    assert email_mock.call_args.kwargs["token"] == "token"


@pytest.mark.asyncio
async def test_confirm_password_reset_accepts_valid_token() -> None:
    with patch(
        "bifrostnms.api.auth.reset_password", new=AsyncMock(return_value=account())
    ) as reset_mock:
        result = await confirm_password_reset(
            PasswordResetRequest(token="x" * 32, password="new-secure-password")
        )

    assert result == {"detail": "Password reset"}
    reset_mock.assert_awaited_once_with("x" * 32, "new-secure-password")


@pytest.mark.asyncio
async def test_serialize_user_includes_memberships_and_superuser_realms() -> None:
    user = account(is_superuser=True)
    member_realm = SimpleNamespace(id=uuid4(), name="Member Realm", slug="member")
    extra_realm = SimpleNamespace(id=uuid4(), name="Admin Realm", slug="admin")
    membership = SimpleNamespace(realm=member_realm, role="owner")
    memberships = MagicMock()
    memberships.select_related.return_value = memberships
    memberships.all = AsyncMock(return_value=[membership])
    realms = MagicMock()
    realms.order_by.return_value = realms
    realms.all = AsyncMock(return_value=[member_realm, extra_realm])

    with (
        patch("bifrostnms.api.auth.RealmMembership.filter", return_value=memberships),
        patch("bifrostnms.api.auth.Realm.filter", return_value=realms),
    ):
        result = await serialize_user(user, session(active_realm_id=extra_realm.id))

    assert result.active_realm_id == extra_realm.id
    assert [(realm.slug, realm.role) for realm in result.realms] == [
        ("member", "owner"),
        ("admin", "superuser"),
    ]


@pytest.mark.asyncio
async def test_signup_rejects_existing_email() -> None:
    users = MagicMock()
    users.exists = AsyncMock(return_value=True)
    payload = SignupRequest(
        email="USER@example.com",
        password="long-enough-password",
        first_name="Test",
        last_name="User",
    )

    with (
        patch("bifrostnms.api.auth.User.filter", return_value=users) as filter_mock,
        pytest.raises(HTTPException, match="account already exists") as exc,
    ):
        await signup(payload, request(), Response())

    assert exc.value.status_code == 409
    filter_mock.assert_called_once_with(email="user@example.com")


@pytest.mark.asyncio
async def test_signup_creates_unique_realm_and_session() -> None:
    user = account()
    realm = cast(Realm, SimpleNamespace(id=uuid4()))
    auth_session = session(active_realm_id=realm.id)
    result_user = serialized_user(user.id)
    users = MagicMock()
    users.exists = AsyncMock(return_value=False)
    realms = MagicMock()
    realms.exists = AsyncMock(side_effect=[True, False])
    payload = SignupRequest(
        email="USER@example.com",
        password="long-enough-password",
        first_name=" Test ",
        last_name=" User ",
        realm_name="Home Lab",
    )

    with (
        patch("bifrostnms.api.auth.User.filter", return_value=users),
        patch("bifrostnms.api.auth.User.create", new=AsyncMock(return_value=user)) as create_user,
        patch("bifrostnms.api.auth.Realm.filter", return_value=realms),
        patch(
            "bifrostnms.api.auth.Realm.create", new=AsyncMock(return_value=realm)
        ) as create_realm,
        patch("bifrostnms.api.auth.RealmMembership.create", new=AsyncMock()) as create_member,
        patch(
            "bifrostnms.api.auth.create_verification_token",
            new=AsyncMock(return_value="verification-token"),
        ),
        patch("bifrostnms.api.auth._send_account_email") as email_mock,
        patch("bifrostnms.api.auth.create_session", new=AsyncMock(return_value=auth_session)),
        patch("bifrostnms.api.auth.serialize_user", new=AsyncMock(return_value=result_user)),
    ):
        result = await signup(payload, request(), Response())

    assert result.user == result_user
    assert create_user.await_args is not None
    assert create_user.await_args.kwargs["first_name"] == "Test"
    create_realm.assert_awaited_once_with(name="Home Lab", slug="home-lab-2")
    create_member.assert_awaited_once_with(user=user, realm=realm, role="owner")
    assert email_mock.call_args.kwargs["token"] == "verification-token"


@pytest.mark.asyncio
async def test_login_rejects_unknown_account() -> None:
    payload = LoginRequest(email="user@example.com", password="password")
    with (
        patch("bifrostnms.api.auth.User.filter", return_value=queryset_with_first(None)),
        pytest.raises(HTTPException, match="Invalid email or password") as exc,
    ):
        await login(payload, request(), Response())

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_login_rejects_disabled_account() -> None:
    user = account(is_active=False)
    payload = LoginRequest(email=user.email, password="password")
    with (
        patch("bifrostnms.api.auth.User.filter", return_value=queryset_with_first(user)),
        patch("bifrostnms.api.auth.verify_password", return_value=True),
        pytest.raises(HTTPException, match="Account is disabled") as exc,
    ):
        await login(payload, request(), Response())

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_login_returns_two_factor_challenge() -> None:
    user = account()
    payload = LoginRequest(email=user.email, password="password")
    with (
        patch("bifrostnms.api.auth.User.filter", return_value=queryset_with_first(user)),
        patch("bifrostnms.api.auth.verify_password", return_value=True),
        patch("bifrostnms.api.auth.user_has_two_factor", new=AsyncMock(return_value=True)),
        patch(
            "bifrostnms.api.auth.create_login_challenge",
            new=AsyncMock(return_value="challenge"),
        ),
    ):
        result = await login(payload, request(), Response())

    assert result.requires_two_factor is True
    assert result.challenge_token == "challenge"
    assert result.user is None


@pytest.mark.asyncio
async def test_login_creates_password_session() -> None:
    user = account()
    auth_session = session()
    result_user = serialized_user(user.id)
    payload = LoginRequest(email=user.email, password="password")
    with (
        patch("bifrostnms.api.auth.User.filter", return_value=queryset_with_first(user)),
        patch("bifrostnms.api.auth.verify_password", return_value=True),
        patch("bifrostnms.api.auth.user_has_two_factor", new=AsyncMock(return_value=False)),
        patch(
            "bifrostnms.api.auth.create_session", new=AsyncMock(return_value=auth_session)
        ) as create_mock,
        patch("bifrostnms.api.auth.serialize_user", new=AsyncMock(return_value=result_user)),
    ):
        result = await login(payload, request(), Response())

    assert result.user == result_user
    assert create_mock.await_args is not None
    assert create_mock.await_args.kwargs["auth_method"] == "password"


@pytest.mark.asyncio
async def test_logout_deletes_session() -> None:
    with patch("bifrostnms.api.auth.delete_session", new=AsyncMock()) as delete_mock:
        await logout(request(), Response())

    delete_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_me_serializes_authenticated_user() -> None:
    user = account()
    auth_session = session()
    result_user = serialized_user(user.id)
    with (
        patch(
            "bifrostnms.api.auth.get_session_user",
            new=AsyncMock(return_value=(user, auth_session)),
        ),
        patch("bifrostnms.api.auth.serialize_user", new=AsyncMock(return_value=result_user)),
    ):
        result = await me(request())

    assert result.user == result_user


@pytest.mark.asyncio
async def test_activate_realm_rejects_missing_membership() -> None:
    user = account()
    realm_id = uuid4()
    with (
        patch(
            "bifrostnms.api.auth.get_session_user",
            new=AsyncMock(return_value=(user, session())),
        ),
        patch(
            "bifrostnms.api.auth.RealmMembership.filter",
            return_value=queryset_with_first(None),
        ),
        pytest.raises(HTTPException, match="Realm not found") as exc,
    ):
        await activate_realm(realm_id, request())

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_activate_realm_updates_member_session() -> None:
    user = account()
    realm = SimpleNamespace(id=uuid4())
    membership = SimpleNamespace(realm=realm)
    auth_session = session()
    result_user = serialized_user(user.id)
    with (
        patch(
            "bifrostnms.api.auth.get_session_user",
            new=AsyncMock(return_value=(user, auth_session)),
        ),
        patch(
            "bifrostnms.api.auth.RealmMembership.filter",
            return_value=queryset_with_first(membership),
        ),
        patch("bifrostnms.api.auth.set_active_realm", new=AsyncMock()) as set_mock,
        patch("bifrostnms.api.auth.serialize_user", new=AsyncMock(return_value=result_user)),
    ):
        result = await activate_realm(realm.id, request())

    assert result.user == result_user
    set_mock.assert_awaited_once_with(auth_session, realm.id)


@pytest.mark.asyncio
async def test_activate_realm_allows_superuser_access() -> None:
    user = account(is_superuser=True)
    realm = SimpleNamespace(id=uuid4())
    auth_session = session()
    result_user = serialized_user(user.id)
    with (
        patch(
            "bifrostnms.api.auth.get_session_user",
            new=AsyncMock(return_value=(user, auth_session)),
        ),
        patch("bifrostnms.api.auth.Realm.filter", return_value=queryset_with_first(realm)),
        patch("bifrostnms.api.auth.set_active_realm", new=AsyncMock()),
        patch("bifrostnms.api.auth.serialize_user", new=AsyncMock(return_value=result_user)),
    ):
        result = await activate_realm(realm.id, request())

    assert result.user == result_user


@pytest.mark.asyncio
async def test_security_summary_includes_passkeys_and_recovery_codes() -> None:
    user = account()
    now = datetime.now(UTC)
    credential = SimpleNamespace(
        id=uuid4(),
        name="Laptop",
        device_type="multi_device",
        backed_up=True,
        transports=None,
        created_at=now,
        last_used_at=now,
    )
    credentials = MagicMock()
    credentials.order_by.return_value = credentials
    credentials.all = AsyncMock(return_value=[credential])
    recovery_codes = MagicMock()
    recovery_codes.count = AsyncMock(return_value=4)

    with (
        patch(
            "bifrostnms.api.security.get_session_user",
            new=AsyncMock(return_value=(user, session())),
        ),
        patch("bifrostnms.api.security.WebAuthnCredential.filter", return_value=credentials),
        patch("bifrostnms.api.security.RecoveryCode.filter", return_value=recovery_codes),
        patch("bifrostnms.api.security.user_has_two_factor", new=AsyncMock(return_value=True)),
    ):
        result = await security_summary(request())

    assert result.two_factor_enabled is True
    assert result.recovery_codes_remaining == 4
    assert result.passkeys[0].transports == []
    assert result.passkeys[0].last_used_at == now.isoformat()
