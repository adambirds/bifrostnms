from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from bifrostnms.config import get_settings
from bifrostnms.models import AuthenticationChallenge, User, WebAuthnCredential


CHALLENGE_TTL_MINUTES = 5


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


async def _store_challenge(
    challenge: bytes,
    challenge_type: str,
    *,
    user: User | None = None,
) -> AuthenticationChallenge:
    return await AuthenticationChallenge.create(
        user=user,
        challenge_type=challenge_type,
        challenge_hash=hashlib.sha256(challenge).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(minutes=CHALLENGE_TTL_MINUTES),
        metadata={"challenge": _b64(challenge)},
    )


async def _get_challenge(challenge_id: str, challenge_type: str) -> AuthenticationChallenge:
    challenge = await AuthenticationChallenge.filter(
        id=challenge_id,
        challenge_type=challenge_type,
        consumed_at=None,
    ).select_related("user").first()
    if not challenge or challenge.expires_at <= datetime.now(UTC):
        raise ValueError("WebAuthn challenge expired")
    return challenge


async def registration_options(user: User) -> dict[str, Any]:
    settings = get_settings()
    credentials = await WebAuthnCredential.filter(user=user).all()
    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=user.id.bytes,
        user_name=user.email,
        user_display_name=user.full_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=_unb64(credential.credential_id))
            for credential in credentials
        ],
    )
    challenge = await _store_challenge(options.challenge, "webauthn_registration", user=user)
    return {"challenge_id": str(challenge.id), "options": json.loads(options_to_json(options))}


async def verify_registration(
    user: User,
    challenge_id: str,
    credential: dict[str, Any],
    name: str,
) -> WebAuthnCredential:
    settings = get_settings()
    challenge = await _get_challenge(challenge_id, "webauthn_registration")
    if challenge.user_id != user.id:
        raise ValueError("WebAuthn challenge does not belong to this user")

    expected_challenge = _unb64(str(challenge.metadata["challenge"]))
    verification = verify_registration_response(
        credential=credential,
        expected_challenge=expected_challenge,
        expected_rp_id=settings.webauthn_rp_id,
        expected_origin=settings.webauthn_origin,
        require_user_verification=True,
    )

    stored = await WebAuthnCredential.create(
        user=user,
        credential_id=_b64(verification.credential_id),
        public_key=_b64(verification.credential_public_key),
        sign_count=verification.sign_count,
        name=name.strip() or "Passkey",
        device_type=str(verification.credential_device_type),
        backed_up=verification.credential_backed_up,
        transports=credential.get("response", {}).get("transports", []),
    )
    challenge.consumed_at = datetime.now(UTC)
    await challenge.save(update_fields=["consumed_at"])
    return stored


async def authentication_options() -> dict[str, Any]:
    settings = get_settings()
    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    challenge = await _store_challenge(options.challenge, "webauthn_authentication")
    return {"challenge_id": str(challenge.id), "options": json.loads(options_to_json(options))}


async def verify_authentication(
    challenge_id: str,
    credential: dict[str, Any],
) -> User:
    settings = get_settings()
    challenge = await _get_challenge(challenge_id, "webauthn_authentication")
    credential_id = credential.get("id")
    if not isinstance(credential_id, str):
        raise ValueError("Invalid passkey response")

    stored = await WebAuthnCredential.filter(credential_id=credential_id).select_related("user").first()
    if not stored:
        raise ValueError("Passkey is not registered")

    verification = verify_authentication_response(
        credential=credential,
        expected_challenge=_unb64(str(challenge.metadata["challenge"])),
        expected_rp_id=settings.webauthn_rp_id,
        expected_origin=settings.webauthn_origin,
        credential_public_key=_unb64(stored.public_key),
        credential_current_sign_count=stored.sign_count,
        require_user_verification=True,
    )

    stored.sign_count = verification.new_sign_count
    stored.last_used_at = datetime.now(UTC)
    stored.device_type = str(verification.credential_device_type)
    stored.backed_up = verification.credential_backed_up
    await stored.save(update_fields=["sign_count", "last_used_at", "device_type", "backed_up"])
    challenge.consumed_at = datetime.now(UTC)
    await challenge.save(update_fields=["consumed_at"])
    return stored.user
