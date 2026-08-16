from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from bifrostnms.auth.permissions import require_realm_permission, require_superuser
from bifrostnms.auth.roles import RealmPermission, RealmRole, role_has_permission
from bifrostnms.auth.security import SessionData
from bifrostnms.models import Realm, User


def queryset(value: object) -> MagicMock:
    result = MagicMock()
    result.first = AsyncMock(return_value=value)
    return result


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

    with (
        patch(
            "bifrostnms.auth.permissions.get_session_user",
            new=AsyncMock(return_value=(user, session)),
        ),
        pytest.raises(HTTPException) as exc,
    ):
        await require_superuser(request)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Installation superuser access required"


def test_realm_role_matrix_is_deny_by_default() -> None:
    assert role_has_permission(RealmRole.OWNER, RealmPermission.REALM_DELETE)
    assert role_has_permission(RealmRole.ADMIN, RealmPermission.MEMBERS_MANAGE)
    assert role_has_permission(RealmRole.MEMBER, RealmPermission.MONITORING_MANAGE)
    assert role_has_permission(RealmRole.VIEWER, RealmPermission.MONITORING_READ)
    assert not role_has_permission(RealmRole.ADMIN, RealmPermission.REALM_DELETE)
    assert not role_has_permission(RealmRole.MEMBER, RealmPermission.MEMBERS_MANAGE)
    assert not role_has_permission(RealmRole.VIEWER, RealmPermission.MONITORING_MANAGE)


@pytest.mark.asyncio
async def test_require_realm_permission_requires_active_realm() -> None:
    user = cast(User, SimpleNamespace(is_superuser=False))
    session = cast(SessionData, SimpleNamespace(active_realm_id=None))
    with (
        patch(
            "bifrostnms.auth.permissions.get_session_user",
            new=AsyncMock(return_value=(user, session)),
        ),
        pytest.raises(HTTPException, match="No active realm") as exc,
    ):
        await require_realm_permission(cast(Request, object()), RealmPermission.REALM_READ)

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_require_realm_permission_returns_member_context() -> None:
    realm = cast(Realm, SimpleNamespace(id=uuid4()))
    user = cast(User, SimpleNamespace(is_superuser=False))
    session = cast(SessionData, SimpleNamespace(active_realm_id=realm.id))
    membership = SimpleNamespace(id=uuid4(), role="member")
    with (
        patch(
            "bifrostnms.auth.permissions.get_session_user",
            new=AsyncMock(return_value=(user, session)),
        ),
        patch("bifrostnms.auth.permissions.Realm.filter", return_value=queryset(realm)),
        patch(
            "bifrostnms.auth.permissions.RealmMembership.filter",
            return_value=queryset(membership),
        ),
    ):
        result = await require_realm_permission(
            cast(Request, object()), RealmPermission.MONITORING_MANAGE
        )

    assert result.realm is realm
    assert result.role is RealmRole.MEMBER
    assert result.membership_id == membership.id
    assert result.is_superuser_bypass is False


@pytest.mark.asyncio
async def test_require_realm_permission_hides_missing_membership() -> None:
    realm = cast(Realm, SimpleNamespace(id=uuid4()))
    user = cast(User, SimpleNamespace(is_superuser=False))
    session = cast(SessionData, SimpleNamespace(active_realm_id=realm.id))
    with (
        patch(
            "bifrostnms.auth.permissions.get_session_user",
            new=AsyncMock(return_value=(user, session)),
        ),
        patch("bifrostnms.auth.permissions.Realm.filter", return_value=queryset(realm)),
        patch(
            "bifrostnms.auth.permissions.RealmMembership.filter",
            return_value=queryset(None),
        ),
        pytest.raises(HTTPException, match="Realm not found") as exc,
    ):
        await require_realm_permission(cast(Request, object()), RealmPermission.MONITORING_READ)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_require_realm_permission_rejects_insufficient_role() -> None:
    realm = cast(Realm, SimpleNamespace(id=uuid4()))
    user = cast(User, SimpleNamespace(is_superuser=False))
    session = cast(SessionData, SimpleNamespace(active_realm_id=realm.id))
    membership = SimpleNamespace(id=uuid4(), role="viewer")
    with (
        patch(
            "bifrostnms.auth.permissions.get_session_user",
            new=AsyncMock(return_value=(user, session)),
        ),
        patch("bifrostnms.auth.permissions.Realm.filter", return_value=queryset(realm)),
        patch(
            "bifrostnms.auth.permissions.RealmMembership.filter",
            return_value=queryset(membership),
        ),
        pytest.raises(HTTPException, match="Realm permission denied") as exc,
    ):
        await require_realm_permission(cast(Request, object()), RealmPermission.MONITORING_MANAGE)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_realm_permission_marks_superuser_bypass() -> None:
    realm = cast(Realm, SimpleNamespace(id=uuid4()))
    user = cast(User, SimpleNamespace(is_superuser=True))
    session = cast(SessionData, SimpleNamespace(active_realm_id=realm.id))
    with (
        patch(
            "bifrostnms.auth.permissions.get_session_user",
            new=AsyncMock(return_value=(user, session)),
        ),
        patch("bifrostnms.auth.permissions.Realm.filter", return_value=queryset(realm)),
    ):
        result = await require_realm_permission(
            cast(Request, object()), RealmPermission.REALM_DELETE
        )

    assert result.role is None
    assert result.membership_id is None
    assert result.is_superuser_bypass is True
