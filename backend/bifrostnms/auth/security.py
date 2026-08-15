import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, Response, status
from pwdlib import PasswordHash

from bifrostnms.config import get_settings
from bifrostnms.models import RealmMembership, User, UserSession

password_hash = PasswordHash.recommended()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(
    user: User,
    request: Request,
    response: Response,
    *,
    auth_method: str = "password",
) -> str:
    settings = get_settings()
    token = secrets.token_urlsafe(48)
    membership = await RealmMembership.filter(user=user).select_related("realm").first()
    expires_at = datetime.now(UTC) + timedelta(days=settings.session_ttl_days)

    await UserSession.create(
        user=user,
        active_realm=membership.realm if membership else None,
        token_hash=hash_token(token),
        expires_at=expires_at,
        auth_method=auth_method,
        user_agent=request.headers.get("user-agent", ""),
        ip_address=request.client.host if request.client else None,
    )

    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_days * 24 * 60 * 60,
        domain=settings.cookie_domain,
        path="/",
    )
    return token


async def get_session_user(request: Request) -> tuple[User, UserSession]:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    session = (
        await UserSession.filter(token_hash=hash_token(token))
        .select_related("user", "active_realm")
        .first()
    )
    if not session or session.expires_at <= datetime.now(UTC) or not session.user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    session.last_activity = datetime.now(UTC)
    await session.save(update_fields=["last_activity"])
    return session.user, session
