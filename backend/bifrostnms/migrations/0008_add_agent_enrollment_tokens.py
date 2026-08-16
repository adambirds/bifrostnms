from uuid import uuid4

from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0007_add_observation_hypertables")]

    initial = False

    operations = [
        ops.CreateModel(
            name="AgentEnrolmentToken",
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
                    fields.ForeignKeyField(
                        "models.Agent",
                        source_field="agent_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="enrolment_tokens",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ("token_hash", fields.CharField(unique=True, db_index=True, max_length=64)),
                ("expires_at", fields.DatetimeField(auto_now=False, auto_now_add=False)),
                (
                    "consumed_at",
                    fields.DatetimeField(
                        null=True, db_index=True, auto_now=False, auto_now_add=False
                    ),
                ),
                (
                    "revoked_at",
                    fields.DatetimeField(
                        null=True, db_index=True, auto_now=False, auto_now_add=False
                    ),
                ),
            ],
            options={"table": "agentenrolmenttoken", "app": "models", "pk_attr": "id"},
            bases=["RealmOwnedModel"],
        ),
    ]
