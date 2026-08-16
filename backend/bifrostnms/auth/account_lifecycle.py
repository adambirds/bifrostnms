from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from bifrostnms.auth.security import hash_password, hash_token
from bifrostnms.config import get_settings
from bifrostnms.models import AuthenticationChallenge, User


async def create_account_token(user: User, challenge_type: str, ttl: timedelta) -> str:
    await AuthenticationChallenge.filter(
        user=user, challenge_type=challenge_type, consumed_at=None
    ).update(consumed_at=datetime.now(UTC))
    token = secrets.token_urlsafe(32)
    await AuthenticationChallenge.create(
        user=user,
        challenge_type=challenge_type,
        challenge_hash=hash_token(token),
        expires_at=datetime.now(UTC) + ttl,
    )
    return token


async def consume_account_token(token: str, challenge_type: str) -> User | None:
    challenge = (
        await AuthenticationChallenge.filter(
            challenge_type=challenge_type,
            challenge_hash=hash_token(token),
            consumed_at=None,
            expires_at__gt=datetime.now(UTC),
        )
        .select_related("user")
        .first()
    )
    if challenge is None or challenge.user is None or not challenge.user.is_active:
        return None
    challenge.consumed_at = datetime.now(UTC)
    await challenge.save(update_fields=["consumed_at"])
    return challenge.user


async def create_verification_token(user: User) -> str:
    settings = get_settings()
    return await create_account_token(
        user, "email_verification", timedelta(hours=settings.email_verification_ttl_hours)
    )


async def create_password_reset_token(user: User) -> str:
    settings = get_settings()
    return await create_account_token(
        user, "password_reset", timedelta(minutes=settings.password_reset_ttl_minutes)
    )


async def verify_email_token(token: str) -> User | None:
    user = await consume_account_token(token, "email_verification")
    if user is not None and not user.email_verified:
        user.email_verified = True
        await user.save(update_fields=["email_verified", "updated_at"])
    return user


async def reset_password(token: str, password: str) -> User | None:
    user = await consume_account_token(token, "password_reset")
    if user is not None:
        user.password_hash = hash_password(password)
        user.session_version += 1
        await user.save(update_fields=["password_hash", "session_version", "updated_at"])
    return user
