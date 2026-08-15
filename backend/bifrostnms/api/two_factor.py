from fastapi import APIRouter, HTTPException, Request, Response, status

from bifrostnms.api.auth import serialize_user
from bifrostnms.auth.security import create_session, get_session_user
from bifrostnms.auth.two_factor import (
    consume_login_challenge,
    create_totp_setup,
    user_has_two_factor,
    verify_totp_setup,
    verify_two_factor,
)
from bifrostnms.models import RecoveryCode, TwoFactorMethod
from bifrostnms.schemas.auth import (
    AuthResponse,
    RecoveryCodesResponse,
    TotpSetupResponse,
    TotpSetupVerifyRequest,
    TwoFactorVerifyRequest,
)

router = APIRouter(prefix="/auth/2fa", tags=["authentication"])


@router.post("/challenge/verify", response_model=AuthResponse)
async def verify_login_challenge(
    payload: TwoFactorVerifyRequest, request: Request, response: Response
) -> AuthResponse:
    user = await consume_login_challenge(payload.challenge_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="2FA challenge expired"
        )
    if not await verify_two_factor(user, payload.code, recovery=payload.recovery_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code"
        )
    session = await create_session(user, request, response, auth_method="password+2fa")
    return AuthResponse(user=await serialize_user(user, session))


@router.post("/totp/setup", response_model=TotpSetupResponse)
async def setup_totp(request: Request) -> TotpSetupResponse:
    user, _ = await get_session_user(request)
    method, secret, uri = await create_totp_setup(user)
    return TotpSetupResponse(method_id=method.id, secret=secret, provisioning_uri=uri)


@router.post("/totp/verify", response_model=RecoveryCodesResponse)
async def verify_totp(payload: TotpSetupVerifyRequest, request: Request) -> RecoveryCodesResponse:
    user, _ = await get_session_user(request)
    try:
        codes = await verify_totp_setup(user, str(payload.method_id), payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RecoveryCodesResponse(recovery_codes=codes)


@router.delete("/totp", status_code=status.HTTP_204_NO_CONTENT)
async def disable_totp(request: Request) -> None:
    user, _ = await get_session_user(request)
    await TwoFactorMethod.filter(user=user, method_type="totp").delete()
    await RecoveryCode.filter(user=user).delete()


@router.get("/enabled")
async def two_factor_enabled(request: Request) -> dict[str, bool]:
    user, _ = await get_session_user(request)
    return {"enabled": await user_has_two_factor(user)}
