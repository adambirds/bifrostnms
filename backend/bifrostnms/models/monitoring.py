from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from tortoise import fields
from tortoise.models import Model

from .auth import Realm


class ProbeType(StrEnum):
    ICMP = "icmp"
    HTTP = "http"
    TCP = "tcp"
    DNS = "dns"
    TLS = "tls"


class RealmOwnedModel(Model):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    realm_id: uuid.UUID
    realm: fields.ForeignKeyRelation[Realm] = fields.ForeignKeyField(
        "models.Realm", related_name=False, on_delete=fields.RESTRICT
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        abstract = True


class Agent(RealmOwnedModel):
    name = fields.CharField(max_length=200)
    description = fields.TextField(null=True)
    enabled = fields.BooleanField(default=True)
    archived_at = fields.DatetimeField(null=True, db_index=True)

    class Meta:
        unique_together = (("realm", "name"),)


class AgentGroup(RealmOwnedModel):
    parent_id: uuid.UUID | None
    parent: fields.ForeignKeyNullableRelation[AgentGroup] = fields.ForeignKeyField(
        "models.AgentGroup",
        related_name="children",
        null=True,
        on_delete=fields.RESTRICT,
    )
    name = fields.CharField(max_length=200)
    description = fields.TextField(null=True)
    enabled = fields.BooleanField(default=True)
    archived_at = fields.DatetimeField(null=True, db_index=True)


class AgentGroupMembership(Model):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    realm_id: uuid.UUID
    realm: fields.ForeignKeyRelation[Realm] = fields.ForeignKeyField(
        "models.Realm", related_name=False, on_delete=fields.RESTRICT
    )
    agent_group: fields.ForeignKeyRelation[AgentGroup] = fields.ForeignKeyField(
        "models.AgentGroup", related_name="memberships", on_delete=fields.CASCADE
    )
    agent_group_id: uuid.UUID
    agent_id: uuid.UUID
    agent: fields.ForeignKeyRelation[Agent] = fields.ForeignKeyField(
        "models.Agent", related_name="group_memberships", on_delete=fields.CASCADE
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        unique_together = (("realm", "agent_group", "agent"),)


class AgentCredential(RealmOwnedModel):
    agent: fields.ForeignKeyRelation[Agent] = fields.ForeignKeyField(
        "models.Agent", related_name="credentials", on_delete=fields.CASCADE
    )
    name = fields.CharField(max_length=120)
    credential_hash = fields.CharField(max_length=128)
    last_used_at = fields.DatetimeField(null=True)
    expires_at = fields.DatetimeField(null=True)
    revoked_at = fields.DatetimeField(null=True, db_index=True)

    class Meta:
        unique_together = (("realm", "agent", "name"),)


class AgentEnrolmentToken(RealmOwnedModel):
    agent_id: uuid.UUID
    agent: fields.ForeignKeyRelation[Agent] = fields.ForeignKeyField(
        "models.Agent", related_name="enrolment_tokens", on_delete=fields.CASCADE
    )
    token_hash = fields.CharField(max_length=64, unique=True, db_index=True)
    expires_at = fields.DatetimeField()
    consumed_at = fields.DatetimeField(null=True, db_index=True)
    revoked_at = fields.DatetimeField(null=True, db_index=True)


class Target(RealmOwnedModel):
    name = fields.CharField(max_length=200)
    description = fields.TextField(null=True)
    address = fields.CharField(max_length=253)
    enabled = fields.BooleanField(default=True)
    archived_at = fields.DatetimeField(null=True, db_index=True)

    class Meta:
        unique_together = (("realm", "name"),)


class TargetGroup(RealmOwnedModel):
    parent_id: uuid.UUID | None
    parent: fields.ForeignKeyNullableRelation[TargetGroup] = fields.ForeignKeyField(
        "models.TargetGroup",
        related_name="children",
        null=True,
        on_delete=fields.RESTRICT,
    )
    name = fields.CharField(max_length=200)
    description = fields.TextField(null=True)
    archived_at = fields.DatetimeField(null=True, db_index=True)


class TargetGroupMembership(Model):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    realm_id: uuid.UUID
    realm: fields.ForeignKeyRelation[Realm] = fields.ForeignKeyField(
        "models.Realm", related_name=False, on_delete=fields.RESTRICT
    )
    target_group: fields.ForeignKeyRelation[TargetGroup] = fields.ForeignKeyField(
        "models.TargetGroup", related_name="memberships", on_delete=fields.CASCADE
    )
    target_group_id: uuid.UUID
    target_id: uuid.UUID
    target: fields.ForeignKeyRelation[Target] = fields.ForeignKeyField(
        "models.Target", related_name="group_memberships", on_delete=fields.CASCADE
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        unique_together = (("realm", "target_group", "target"),)


class Monitor(RealmOwnedModel):
    target_id: uuid.UUID
    target: fields.ForeignKeyRelation[Target] = fields.ForeignKeyField(
        "models.Target", related_name="monitors", on_delete=fields.RESTRICT
    )
    name = fields.CharField(max_length=200)
    description = fields.TextField(null=True)
    probe_type = fields.CharEnumField(ProbeType, max_length=16)
    interval_seconds = fields.IntField()
    timeout_seconds = fields.IntField()
    configuration = fields.JSONField[dict[str, Any]](default=dict)
    enabled = fields.BooleanField(default=True)
    revision = fields.IntField(default=1)
    archived_at = fields.DatetimeField(null=True, db_index=True)

    class Meta:
        unique_together = (("realm", "name"),)


class MonitorAgentAssignment(RealmOwnedModel):
    monitor_id: uuid.UUID
    monitor: fields.ForeignKeyRelation[Monitor] = fields.ForeignKeyField(
        "models.Monitor", related_name="agent_assignments", on_delete=fields.CASCADE
    )
    agent: fields.ForeignKeyRelation[Agent] = fields.ForeignKeyField(
        "models.Agent", related_name="monitor_assignments", on_delete=fields.CASCADE
    )
    agent_id: uuid.UUID
    enabled = fields.BooleanField(default=True)

    class Meta:
        unique_together = (("realm", "monitor", "agent"),)


class MonitorAgentGroupAssignment(RealmOwnedModel):
    monitor_id: uuid.UUID
    monitor: fields.ForeignKeyRelation[Monitor] = fields.ForeignKeyField(
        "models.Monitor", related_name="agent_group_assignments", on_delete=fields.CASCADE
    )
    agent_group: fields.ForeignKeyRelation[AgentGroup] = fields.ForeignKeyField(
        "models.AgentGroup", related_name="monitor_assignments", on_delete=fields.CASCADE
    )
    agent_group_id: uuid.UUID
    enabled = fields.BooleanField(default=True)

    class Meta:
        unique_together = (("realm", "monitor", "agent_group"),)


class AgentConfigurationState(RealmOwnedModel):
    agent: fields.OneToOneRelation[Agent] = fields.OneToOneField(
        "models.Agent", related_name="configuration_state", on_delete=fields.CASCADE
    )
    desired_revision = fields.BigIntField(default=0)
    desired_content_hash = fields.CharField(max_length=64, default="")
    acknowledged_revision = fields.BigIntField(default=0)
    acknowledged_at = fields.DatetimeField(null=True)


class AgentConfigurationSnapshot(Model):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    realm: fields.ForeignKeyRelation[Realm] = fields.ForeignKeyField(
        "models.Realm", related_name=False, on_delete=fields.RESTRICT
    )
    agent: fields.ForeignKeyRelation[Agent] = fields.ForeignKeyField(
        "models.Agent", related_name="configuration_snapshots", on_delete=fields.RESTRICT
    )
    revision = fields.BigIntField()
    content_hash = fields.CharField(max_length=64)
    configuration = fields.JSONField[dict[str, Any]]()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        unique_together = (("realm", "agent", "revision"),)
