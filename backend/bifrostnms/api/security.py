from fastapi import APIRouter, Request

from bifrostnms.auth.security import get_session_user
from bifrostnms.auth.two_factor import user_has_two_factor
from bifrostnms.models import RecoveryCode, WebAuthnCredential
from bifrostnms.schemas.auth import PasskeySummary, SecuritySummary

router = APIRouter(prefix="/auth/security", tags=["authentication"])


@router.get("", response_model=SecuritySummary)
async def security_summary(request: Request) -> SecuritySummary:
    user, _ = await get_session_user(request)
    credentials = await WebAuthnCredential.filter(user=user).order_by("-created_at").all()
    recovery_codes_remaining = await RecoveryCode.filter(user=user, used_at=None).count()
    return SecuritySummary(
        two_factor_enabled=await user_has_two_factor(user),
        recovery_codes_remaining=recovery_codes_remaining,
        passkeys=[
            PasskeySummary(
                id=credential.id,
                name=credential.name,
                device_type=credential.device_type,
                backed_up=credential.backed_up,
                transports=list(credential.transports or []),
                created_at=credential.created_at.isoformat(),
                last_used_at=credential.last_used_at.isoformat()
                if credential.last_used_at
                else None,
            )
            for credential in credentials
        ],
    )
