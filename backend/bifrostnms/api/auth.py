import re
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status

from bifrostnms.auth.account_lifecycle import (
    create_password_reset_token,
    create_verification_token,
    reset_password,
    verify_email_token,
)
from bifrostnms.auth.security import (
    SessionData,
    create_session,
    delete_session,
    get_session_user,
    hash_password,
    normalize_email,
    set_active_realm,
    verify_password,
)
from bifrostnms.auth.two_factor import create_login_challenge, user_has_two_factor
from bifrostnms.config import get_settings
from bifrostnms.models import Realm, RealmMembership, User
from bifrostnms.schemas.auth import (
    AuthResponse,
    EmailRequest,
    LoginRequest,
    LoginResponse,
    PasswordResetRequest,
    RealmSummary,
    SignupRequest,
    TokenRequest,
    UserResponse,
)
from bifrostnms.tasks.email import send_email

router = APIRouter(prefix="/auth", tags=["authentication"])


def _send_account_email(*, email: str, subject: str, path: str, token: str) -> None:
    url = f"{get_settings().auth_frontend_url.rstrip('/')}{path}?{urlencode({'token': token})}"
    send_email.delay(
        to=[email],
        subject=subject,
        text=f"Open this link to continue:\n\n{url}\n\nIf you did not request this, ignore this email.",
    )


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return value or "realm"


async def serialize_user(user: User, session: SessionData | None = None) -> UserResponse:
    memberships = await RealmMembership.filter(user=user).select_related("realm").all()
    realm_summaries = {
        membership.realm.id: RealmSummary(
            id=membership.realm.id,
            name=membership.realm.name,
            slug=membership.realm.slug,
            role=membership.role,
        )
        for membership in memberships
    }

    if user.is_superuser:
        for realm in await Realm.filter(is_active=True).order_by("name").all():
            realm_summaries.setdefault(
                realm.id,
                RealmSummary(id=realm.id, name=realm.name, slug=realm.slug, role="superuser"),
            )

    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        email_verified=user.email_verified,
        is_superuser=user.is_superuser,
        active_realm_id=session.active_realm_id if session else None,
        realms=list(realm_summaries.values()),
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, request: Request, response: Response) -> AuthResponse:
    email = normalize_email(str(payload.email))
    if await User.filter(email=email).exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An account already exists for that email"
        )

    user = await User.create(
        email=email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
    )

    realm_name = payload.realm_name or f"{payload.first_name.strip()}'s Realm"
    base_slug = slugify(realm_name)
    slug = base_slug
    counter = 2
    while await Realm.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    realm = await Realm.create(name=realm_name, slug=slug)
    await RealmMembership.create(user=user, realm=realm, role="owner")
    token = await create_verification_token(user)
    _send_account_email(
        email=user.email,
        subject="Verify your BifrostNMS email",
        path="/verify-email",
        token=token,
    )
    session = await create_session(user, request, response)
    return AuthResponse(user=await serialize_user(user, session))


@router.post("/email-verification/request", status_code=status.HTTP_202_ACCEPTED)
async def request_email_verification(request: Request) -> dict[str, str]:
    user, _ = await get_session_user(request)
    if not user.email_verified:
        token = await create_verification_token(user)
        _send_account_email(
            email=user.email,
            subject="Verify your BifrostNMS email",
            path="/verify-email",
            token=token,
        )
    return {"detail": "Verification email requested"}


@router.post("/email-verification/confirm")
async def confirm_email_verification(payload: TokenRequest) -> dict[str, str]:
    if await verify_email_token(payload.token) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token"
        )
    return {"detail": "Email verified"}


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(payload: EmailRequest) -> dict[str, str]:
    user = await User.filter(email=normalize_email(str(payload.email)), is_active=True).first()
    if user is not None:
        token = await create_password_reset_token(user)
        _send_account_email(
            email=user.email,
            subject="Reset your BifrostNMS password",
            path="/reset-password",
            token=token,
        )
    return {"detail": "If the account exists, a reset email has been sent"}


@router.post("/password/reset")
async def confirm_password_reset(payload: PasswordResetRequest) -> dict[str, str]:
    if await reset_password(payload.token, payload.password) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token"
        )
    return {"detail": "Password reset"}


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> LoginResponse:
    user = await User.filter(email=normalize_email(str(payload.email))).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    if await user_has_two_factor(user):
        return LoginResponse(
            requires_two_factor=True, challenge_token=await create_login_challenge(user)
        )

    session = await create_session(user, request, response, auth_method="password")
    return LoginResponse(user=await serialize_user(user, session))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    await delete_session(request, response)


@router.get("/me", response_model=AuthResponse)
async def me(request: Request) -> AuthResponse:
    user, session = await get_session_user(request)
    return AuthResponse(user=await serialize_user(user, session))


@router.post("/realm/{realm_id}/activate", response_model=AuthResponse)
async def activate_realm(realm_id: UUID, request: Request) -> AuthResponse:
    user, session = await get_session_user(request)

    if user.is_superuser:
        realm = await Realm.filter(id=realm_id, is_active=True).first()
        if not realm:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Realm not found")
    else:
        membership = (
            await RealmMembership.filter(user=user, realm_id=realm_id)
            .select_related("realm")
            .first()
        )
        if not membership:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Realm not found")
        realm = membership.realm

    await set_active_realm(session, realm.id)
    return AuthResponse(user=await serialize_user(user, session))
