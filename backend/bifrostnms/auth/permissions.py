from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, Request, status

from bifrostnms.auth.security import SessionData, get_session_user
from bifrostnms.auth.roles import RealmPermission, RealmRole, role_has_permission
from bifrostnms.models import Realm, RealmMembership, User


@dataclass(frozen=True, slots=True)
class RealmAuthorization:
    user: User
    session: SessionData
    realm: Realm
    role: RealmRole | None
    membership_id: UUID | None
    is_superuser_bypass: bool


async def require_superuser(request: Request) -> tuple[User, SessionData]:
    """Require an authenticated installation superuser for an endpoint."""
    user, session = await get_session_user(request)
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Installation superuser access required",
        )
    return user, session


async def require_realm_permission(
    request: Request, permission: RealmPermission
) -> RealmAuthorization:
    """Authorize a request against its active realm and one named permission."""
    user, session = await get_session_user(request)
    if session.active_realm_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active realm selected",
        )

    realm = await Realm.filter(id=session.active_realm_id, is_active=True).first()
    if realm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Realm not found")

    if user.is_superuser:
        return RealmAuthorization(
            user=user,
            session=session,
            realm=realm,
            role=None,
            membership_id=None,
            is_superuser_bypass=True,
        )

    membership = await RealmMembership.filter(user=user, realm=realm).first()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Realm not found")

    try:
        role = RealmRole(membership.role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Realm permission denied",
        ) from exc
    if not role_has_permission(role, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Realm permission denied",
        )

    return RealmAuthorization(
        user=user,
        session=session,
        realm=realm,
        role=role,
        membership_id=membership.id,
        is_superuser_bypass=False,
    )
