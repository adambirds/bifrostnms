from fastapi import APIRouter, HTTPException, Request, Response, status

from bifrostnms.api.auth import serialize_user
from bifrostnms.auth.security import create_session, get_session_user
from bifrostnms.auth.webauthn import (
    authentication_options,
    registration_options,
    verify_authentication,
    verify_registration,
)
from bifrostnms.models import WebAuthnCredential
from bifrostnms.schemas.auth import (
    AuthResponse,
    WebAuthnAuthenticationVerifyRequest,
    WebAuthnOptionsResponse,
    WebAuthnRegistrationVerifyRequest,
)

router = APIRouter(prefix="/auth/webauthn", tags=["authentication"])


@router.post("/register/options", response_model=WebAuthnOptionsResponse)
async def register_options(request: Request) -> WebAuthnOptionsResponse:
    user, _ = await get_session_user(request)
    return WebAuthnOptionsResponse(**await registration_options(user))


@router.post("/register/verify", status_code=status.HTTP_201_CREATED)
async def register_verify(
    payload: WebAuthnRegistrationVerifyRequest,
    request: Request,
) -> dict[str, str]:
    user, _ = await get_session_user(request)
    try:
        credential = await verify_registration(
            user,
            str(payload.challenge_id),
            payload.credential,
            payload.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"id": str(credential.id), "name": credential.name}


@router.post("/authenticate/options", response_model=WebAuthnOptionsResponse)
async def authenticate_options() -> WebAuthnOptionsResponse:
    return WebAuthnOptionsResponse(**await authentication_options())


@router.post("/authenticate/verify", response_model=AuthResponse)
async def authenticate_verify(
    payload: WebAuthnAuthenticationVerifyRequest,
    request: Request,
    response: Response,
) -> AuthResponse:
    try:
        user = await verify_authentication(str(payload.challenge_id), payload.credential)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    await create_session(user, request, response, auth_method="passkey")
    return AuthResponse(user=await serialize_user(user))


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_passkey(credential_id: str, request: Request) -> None:
    user, _ = await get_session_user(request)
    deleted = await WebAuthnCredential.filter(id=credential_id, user=user).delete()
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passkey not found")
