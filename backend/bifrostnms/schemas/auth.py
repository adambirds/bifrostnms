from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    first_name: str = Field(min_length=1, max_length=150)
    last_name: str = Field(min_length=1, max_length=150)
    realm_name: str | None = Field(default=None, max_length=200)


class EmailRequest(BaseModel):
    email: EmailStr


class TokenRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class PasswordResetRequest(TokenRequest):
    password: str = Field(min_length=12, max_length=256)


class RealmSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    role: str


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    full_name: str
    email_verified: bool
    is_superuser: bool
    active_realm_id: UUID | None
    realms: list[RealmSummary]


class AuthResponse(BaseModel):
    user: UserResponse


class LoginResponse(BaseModel):
    user: UserResponse | None = None
    requires_two_factor: bool = False
    challenge_token: str | None = None


class TwoFactorVerifyRequest(BaseModel):
    challenge_token: str
    code: str = Field(min_length=6, max_length=32)
    recovery_code: bool = False


class TotpSetupResponse(BaseModel):
    method_id: UUID
    secret: str
    provisioning_uri: str


class TotpSetupVerifyRequest(BaseModel):
    method_id: UUID
    code: str = Field(min_length=6, max_length=8)


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class WebAuthnOptionsResponse(BaseModel):
    challenge_id: UUID
    options: dict[str, Any]


class WebAuthnRegistrationVerifyRequest(BaseModel):
    challenge_id: UUID
    credential: dict[str, Any]
    name: str = Field(default="Passkey", max_length=120)


class WebAuthnAuthenticationVerifyRequest(BaseModel):
    challenge_id: UUID
    credential: dict[str, Any]


class PasskeySummary(BaseModel):
    id: UUID
    name: str
    device_type: str
    backed_up: bool
    transports: list[str]
    created_at: str
    last_used_at: str | None


class SecuritySummary(BaseModel):
    two_factor_enabled: bool
    recovery_codes_remaining: int
    passkeys: list[PasskeySummary]
