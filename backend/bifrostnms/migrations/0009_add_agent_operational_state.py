import functools
from json import dumps, loads
from uuid import uuid4

from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0008_add_agent_enrollment_tokens")]

    initial = False

    operations = [
        ops.CreateModel(
            name="AgentOperationalState",
            fields=[
                (
                    "id",
                    fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True),
                ),
                (
                    "realm",
                    fields.ForeignKeyField(
                        "models.Realm",
                        source_field="realm_id",
                        db_constraint=True,
                        to_field="id",
                        related_name=False,
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ("updated_at", fields.DatetimeField(auto_now=True, auto_now_add=False)),
                (
                    "agent",
                    fields.OneToOneField(
                        "models.Agent",
                        source_field="agent_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="operational_state",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    "last_heartbeat_at",
                    fields.DatetimeField(db_index=True, auto_now=False, auto_now_add=False),
                ),
                ("agent_version", fields.CharField(max_length=120)),
                ("platform", fields.CharField(max_length=120)),
                ("architecture", fields.CharField(max_length=120)),
                ("hostname", fields.CharField(max_length=253)),
                (
                    "capabilities",
                    fields.JSONField(
                        default=dict,
                        encoder=functools.partial(dumps, separators=(",", ":")),
                        decoder=loads,
                    ),
                ),
                ("active_configuration_revision", fields.BigIntField(default=0)),
                ("known_desired_configuration_revision", fields.BigIntField(default=0)),
                ("queue_depth", fields.BigIntField(default=0)),
                ("queue_bytes", fields.BigIntField(default=0)),
                (
                    "oldest_pending_observation_at",
                    fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
                ),
                ("database_health", fields.CharField(max_length=16)),
                ("scheduler_state", fields.CharField(max_length=16)),
                ("agent_time", fields.DatetimeField(auto_now=False, auto_now_add=False)),
                ("clock_offset_ms", fields.BigIntField()),
                (
                    "warnings",
                    fields.JSONField(
                        default=list,
                        encoder=functools.partial(dumps, separators=(",", ":")),
                        decoder=loads,
                    ),
                ),
            ],
            options={"table": "agentoperationalstate", "app": "models", "pk_attr": "id"},
            bases=["RealmOwnedModel"],
        ),
    ]
