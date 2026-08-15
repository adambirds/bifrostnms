from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, Request, Response, status
from pwdlib import PasswordHash

from bifrostnms.auth.redis import get_redis
from bifrostnms.config import get_settings
from bifrostnms.models import Realm, RealmMembership, User

password_hash = PasswordHash.recommended()


@dataclass(slots=True)
class SessionData:
    user_id: UUID
    active_realm_id: UUID | None
    auth_method: str
    created_at: datetime
    last_activity: datetime
    user_agent: str
    ip_address: str | None
    redis_key: str

    def to_json(self) -> str:
        data = asdict(self)
        data.pop("redis_key", None)
        data["user_id"] = str(self.user_id)
        data["active_realm_id"] = str(self.active_realm_id) if self.active_realm_id else None
        data["created_at"] = self.created_at.isoformat()
        data["last_activity"] = self.last_activity.isoformat()
        return json.dumps(data, separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str, *, redis_key: str) -> SessionData:
        data = json.loads(value)
        return cls(
            user_id=UUID(data["user_id"]),
            active_realm_id=UUID(data["active_realm_id"]) if data.get("active_realm_id") else None,
            auth_method=data["auth_method"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_activity=datetime.fromisoformat(data["last_activity"]),
            user_agent=data.get("user_agent", ""),
            ip_address=data.get("ip_address"),
            redis_key=redis_key,
        )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session_key(token: str) -> str:
    settings = get_settings()
    return f"{settings.session_key_prefix}{hash_token(token)}"


async def _initial_realm_id(user: User) -> UUID | None:
    membership = await RealmMembership.filter(user=user).select_related("realm").first()
    if membership:
        return membership.realm.id

    if user.is_superuser:
        realm = await Realm.filter(is_active=True).order_by("created_at").first()
        if realm:
            return realm.id

    return None


async def create_session(
    user: User,
    request: Request,
    response: Response,
    *,
    auth_method: str = "password",
) -> SessionData:
    settings = get_settings()
    token = secrets.token_urlsafe(48)
    redis_key = _session_key(token)
    now = datetime.now(UTC)
    session = SessionData(
        user_id=user.id,
        active_realm_id=await _initial_realm_id(user),
        auth_method=auth_method,
        created_at=now,
        last_activity=now,
        user_agent=request.headers.get("user-agent", ""),
        ip_address=request.client.host if request.client else None,
        redis_key=redis_key,
    )
    redis = get_redis()
    await redis.set(redis_key, session.to_json(), ex=settings.session_ttl_seconds)

    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
        domain=settings.cookie_domain,
        path="/",
    )
    return session


async def get_session_user(request: Request) -> tuple[User, SessionData]:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    redis_key = _session_key(token)
    redis = get_redis()
    raw = await redis.get(redis_key)
    if raw is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    session = SessionData.from_json(raw, redis_key=redis_key)
    user = await User.filter(id=session.user_id, is_active=True).first()
    if user is None:
        await redis.delete(redis_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    session.last_activity = datetime.now(UTC)
    await redis.set(redis_key, session.to_json(), ex=settings.session_ttl_seconds)
    return user, session


async def set_active_realm(session: SessionData, realm_id: UUID) -> None:
    settings = get_settings()
    session.active_realm_id = realm_id
    session.last_activity = datetime.now(UTC)
    await get_redis().set(session.redis_key, session.to_json(), ex=settings.session_ttl_seconds)


async def delete_session(request: Request, response: Response) -> None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await get_redis().delete(_session_key(token))
    response.delete_cookie(settings.session_cookie_name, path="/", domain=settings.cookie_domain)
