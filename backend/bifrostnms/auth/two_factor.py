from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import pyotp
from cryptography.fernet import Fernet

from bifrostnms.config import get_settings
from bifrostnms.models import AuthenticationChallenge, RecoveryCode, TwoFactorMethod, User

CHALLENGE_TTL_MINUTES = 5
RECOVERY_CODE_COUNT = 10
RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _fernet() -> Fernet:
    settings = get_settings()
    digest = hashlib.sha256(settings.auth_encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_secret(secret: str) -> str:
    return _fernet().decrypt(secret.encode("ascii")).decode("utf-8")


def hash_recovery_code(code: str) -> str:
    normalized = code.strip().upper().replace(" ", "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def generate_recovery_code() -> str:
    return "-".join("".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(4)) for _ in range(3))


async def create_totp_setup(user: User) -> tuple[TwoFactorMethod, str, str]:
    await TwoFactorMethod.filter(user=user, method_type="totp", is_enabled=False).delete()
    secret = pyotp.random_base32()
    method = await TwoFactorMethod.create(
        user=user,
        method_type="totp",
        secret_encrypted=encrypt_secret(secret),
        is_enabled=False,
    )
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="BifrostNMS")
    return method, secret, uri


async def verify_totp_setup(user: User, method_id: str, code: str) -> list[str]:
    method = await TwoFactorMethod.filter(id=method_id, user=user, method_type="totp").first()
    if not method:
        raise ValueError("TOTP setup not found")
    secret = decrypt_secret(method.secret_encrypted)
    if not pyotp.TOTP(secret).verify(code.strip(), valid_window=1):
        raise ValueError("Invalid verification code")

    method.is_enabled = True
    method.verified_at = datetime.now(UTC)
    await method.save(update_fields=["is_enabled", "verified_at"])

    await RecoveryCode.filter(user=user).delete()
    codes = [generate_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    await RecoveryCode.bulk_create(
        [RecoveryCode(user=user, code_hash=hash_recovery_code(code)) for code in codes]
    )
    return codes


async def user_has_two_factor(user: User) -> bool:
    return await TwoFactorMethod.filter(user=user, method_type="totp", is_enabled=True).exists()


async def verify_two_factor(user: User, code: str, recovery: bool = False) -> bool:
    if recovery:
        code_hash = hash_recovery_code(code)
        recovery_code = await RecoveryCode.filter(
            user=user, code_hash=code_hash, used_at=None
        ).first()
        if not recovery_code:
            return False
        recovery_code.used_at = datetime.now(UTC)
        await recovery_code.save(update_fields=["used_at"])
        return True

    method = await TwoFactorMethod.filter(user=user, method_type="totp", is_enabled=True).first()
    if not method:
        return False
    secret = decrypt_secret(method.secret_encrypted)
    valid = pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
    if valid:
        method.last_used_at = datetime.now(UTC)
        await method.save(update_fields=["last_used_at"])
    return bool(valid)


async def create_login_challenge(user: User) -> str:
    token = secrets.token_urlsafe(48)
    now = datetime.now(UTC)
    await AuthenticationChallenge.filter(
        user=user, challenge_type="two_factor_login", consumed_at=None
    ).delete()
    await AuthenticationChallenge.create(
        user=user,
        challenge_type="two_factor_login",
        challenge_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        expires_at=now + timedelta(minutes=CHALLENGE_TTL_MINUTES),
    )
    return token


async def consume_login_challenge(token: str) -> User | None:
    challenge = (
        await AuthenticationChallenge.filter(
            challenge_type="two_factor_login",
            challenge_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            consumed_at=None,
        )
        .select_related("user")
        .first()
    )
    if not challenge or challenge.expires_at <= datetime.now(UTC) or not challenge.user:
        return None
    challenge.consumed_at = datetime.now(UTC)
    await challenge.save(update_fields=["consumed_at"])
    return challenge.user
