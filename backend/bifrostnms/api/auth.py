import re
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status

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
from bifrostnms.models import Realm, RealmMembership, User
from bifrostnms.schemas.auth import (
    AuthResponse,
    LoginRequest,
    LoginResponse,
    RealmSummary,
    SignupRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return value or "realm"


async def serialize_user(user: User, session: SessionData | None = None) -> UserResponse:
    memberships = await RealmMembership.filter(user=user).select_related("realm").all()
    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        email_verified=user.email_verified,
        active_realm_id=session.active_realm_id if session else None,
        realms=[
            RealmSummary(id=m.realm.id, name=m.realm.name, slug=m.realm.slug, role=m.role)
            for m in memberships
        ],
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, request: Request, response: Response) -> AuthResponse:
    email = normalize_email(str(payload.email))
    if await User.filter(email=email).exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account already exists for that email")

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
    session = await create_session(user, request, response)
    return AuthResponse(user=await serialize_user(user, session))


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> LoginResponse:
    user = await User.filter(email=normalize_email(str(payload.email))).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    if await user_has_two_factor(user):
        return LoginResponse(requires_two_factor=True, challenge_token=await create_login_challenge(user))

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
    membership = await RealmMembership.filter(user=user, realm_id=realm_id).select_related("realm").first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Realm not found")
    await set_active_realm(session, membership.realm.id)
    return AuthResponse(user=await serialize_user(user, session))
