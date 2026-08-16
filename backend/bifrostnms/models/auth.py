from __future__ import annotations

import uuid
from typing import Any

from tortoise import fields
from tortoise.models import Model


class TimestampedModel(Model):
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        abstract = True


class User(TimestampedModel):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    email = fields.CharField(max_length=320, unique=True, db_index=True)
    password_hash = fields.CharField(max_length=255)
    first_name = fields.CharField(max_length=150)
    last_name = fields.CharField(max_length=150)
    is_active = fields.BooleanField(default=True)
    is_superuser = fields.BooleanField(default=False)
    email_verified = fields.BooleanField(default=False)
    session_version = fields.IntField(default=1)

    memberships: fields.ReverseRelation[RealmMembership]
    webauthn_credentials: fields.ReverseRelation[WebAuthnCredential]
    two_factor_methods: fields.ReverseRelation[TwoFactorMethod]
    recovery_codes: fields.ReverseRelation[RecoveryCode]
    audit_events: fields.ReverseRelation[AuditEvent]

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Realm(TimestampedModel):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    name = fields.CharField(max_length=200)
    slug = fields.CharField(max_length=120, unique=True, db_index=True)
    is_active = fields.BooleanField(default=True)

    memberships: fields.ReverseRelation[RealmMembership]
    audit_events: fields.ReverseRelation[AuditEvent]


class RealmMembership(TimestampedModel):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
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
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="webauthn_credentials", on_delete=fields.CASCADE
    )
    credential_id = fields.CharField(max_length=1024, unique=True)
    public_key = fields.TextField()
    sign_count = fields.BigIntField(default=0)
    name = fields.CharField(max_length=120, default="Passkey")
    device_type = fields.CharField(max_length=64, default="")
    backed_up = fields.BooleanField(default=False)
    transports = fields.JSONField[list[str]](default=list)
    last_used_at = fields.DatetimeField(null=True)


class TwoFactorMethod(TimestampedModel):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
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
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="recovery_codes", on_delete=fields.CASCADE
    )
    code_hash = fields.CharField(max_length=64, db_index=True)
    used_at = fields.DatetimeField(null=True)


class AuthenticationChallenge(TimestampedModel):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    user: fields.ForeignKeyNullableRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="authentication_challenges", null=True, on_delete=fields.CASCADE
    )
    challenge_type = fields.CharField(max_length=32, db_index=True)
    challenge_hash = fields.CharField(max_length=64, unique=True, db_index=True)
    expires_at = fields.DatetimeField(db_index=True)
    consumed_at = fields.DatetimeField(null=True)
    metadata = fields.JSONField[dict[str, Any]](default=dict)


class AuditEvent(Model):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    occurred_at = fields.DatetimeField(auto_now_add=True, db_index=True)
    realm: fields.ForeignKeyNullableRelation[Realm] = fields.ForeignKeyField(
        "models.Realm", related_name="audit_events", null=True, on_delete=fields.SET_NULL
    )
    actor_user: fields.ForeignKeyNullableRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="audit_events", null=True, on_delete=fields.SET_NULL
    )
    actor_type = fields.CharField(max_length=32)
    action = fields.CharField(max_length=120, db_index=True)
    outcome = fields.CharField(max_length=32, db_index=True)
    target_type = fields.CharField(max_length=80, null=True)
    target_id = fields.CharField(max_length=255, null=True)
    source_ip = fields.CharField(max_length=64, null=True)
    user_agent = fields.CharField(max_length=512, default="")
    superuser_bypass = fields.BooleanField(default=False)
    metadata = fields.JSONField[dict[str, Any]](default=dict)
