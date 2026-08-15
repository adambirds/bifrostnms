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
    active_realm_id: UUID | None
    realms: list[RealmSummary]


class AuthResponse(BaseModel):
    user: UserResponse
