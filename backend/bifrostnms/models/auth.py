from __future__ import annotations

import uuid

from tortoise import fields
from tortoise.models import Model


class TimestampedModel(Model):
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        abstract = True


class User(TimestampedModel):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    email = fields.CharField(max_length=320, unique=True, index=True)
    password_hash = fields.CharField(max_length=255)
    first_name = fields.CharField(max_length=150)
    last_name = fields.CharField(max_length=150)
    is_active = fields.BooleanField(default=True)
    is_staff = fields.BooleanField(default=False)
    email_verified = fields.BooleanField(default=False)

    memberships: fields.ReverseRelation[RealmMembership]
    webauthn_credentials: fields.ReverseRelation[WebAuthnCredential]
    two_factor_methods: fields.ReverseRelation[TwoFactorMethod]
    recovery_codes: fields.ReverseRelation[RecoveryCode]

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Realm(TimestampedModel):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    name = fields.CharField(max_length=200)
    slug = fields.CharField(max_length=120, unique=True, index=True)
    is_active = fields.BooleanField(default=True)

    memberships: fields.ReverseRelation[RealmMembership]


class RealmMembership(TimestampedModel):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="memberships", on_delete=fields.CASCADE
    )
    realm: fields.ForeignKeyRelation[Realm] = fields.ForeignKeyField(
        "models.Realm", related_name="memberships", on_delete=fields.CASCADE
    )
    role = fields.CharField(max_length=32, default="owner")

    class Meta:
        unique_together = (("user", "realm"),)


class WebAuthnCredential(TimestampedModel):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="webauthn_credentials", on_delete=fields.CASCADE
    )
    credential_id = fields.CharField(max_length=1024, unique=True)
    public_key = fields.TextField()
    sign_count = fields.BigIntField(default=0)
    name = fields.CharField(max_length=120, default="Passkey")
    device_type = fields.CharField(max_length=64, default="")
    backed_up = fields.BooleanField(default=False)
    transports = fields.JSONField(default=list)
    last_used_at = fields.DatetimeField(null=True)


class TwoFactorMethod(TimestampedModel):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="two_factor_methods", on_delete=fields.CASCADE
    )
    method_type = fields.CharField(max_length=32, default="totp")
    secret_encrypted = fields.TextField()
    name = fields.CharField(max_length=120, default="Authenticator app")
    is_enabled = fields.BooleanField(default=False)
    verified_at = fields.DatetimeField(null=True)
    last_used_at = fields.DatetimeField(null=True)

    class Meta:
        unique_together = (("user", "method_type"),)


class RecoveryCode(TimestampedModel):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="recovery_codes", on_delete=fields.CASCADE
    )
    code_hash = fields.CharField(max_length=64, index=True)
    used_at = fields.DatetimeField(null=True)


class AuthenticationChallenge(TimestampedModel):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    user: fields.ForeignKeyNullableRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="authentication_challenges", null=True, on_delete=fields.CASCADE
    )
    challenge_type = fields.CharField(max_length=32, index=True)
    challenge_hash = fields.CharField(max_length=64, unique=True, index=True)
    expires_at = fields.DatetimeField(index=True)
    consumed_at = fields.DatetimeField(null=True)
    metadata = fields.JSONField(default=dict)
