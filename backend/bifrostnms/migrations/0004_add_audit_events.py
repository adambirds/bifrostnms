import functools
from json import dumps, loads
from uuid import uuid4

from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0003_add_session_version")]

    initial = False

    operations = [
        ops.CreateModel(
            name="AuditEvent",
            fields=[
                (
                    "id",
                    fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True),
                ),
                (
                    "occurred_at",
                    fields.DatetimeField(db_index=True, auto_now=False, auto_now_add=True),
                ),
                (
                    "realm",
                    fields.ForeignKeyField(
                        "models.Realm",
                        source_field="realm_id",
                        null=True,
                        db_constraint=True,
                        to_field="id",
                        related_name="audit_events",
                        on_delete=OnDelete.SET_NULL,
                    ),
                ),
                (
                    "actor_user",
                    fields.ForeignKeyField(
                        "models.User",
                        source_field="actor_user_id",
                        null=True,
                        db_constraint=True,
                        to_field="id",
                        related_name="audit_events",
                        on_delete=OnDelete.SET_NULL,
                    ),
                ),
                ("actor_type", fields.CharField(max_length=32)),
                ("action", fields.CharField(db_index=True, max_length=120)),
                ("outcome", fields.CharField(db_index=True, max_length=32)),
                ("target_type", fields.CharField(null=True, max_length=80)),
                ("target_id", fields.CharField(null=True, max_length=255)),
                ("source_ip", fields.CharField(null=True, max_length=64)),
                ("user_agent", fields.CharField(default="", max_length=512)),
                ("superuser_bypass", fields.BooleanField(default=False)),
                (
                    "metadata",
                    fields.JSONField(
                        default=dict,
                        encoder=functools.partial(dumps, separators=(",", ":")),
                        decoder=loads,
                    ),
                ),
            ],
            options={"table": "auditevent", "app": "models", "pk_attr": "id"},
            bases=["Model"],
        ),
    ]
