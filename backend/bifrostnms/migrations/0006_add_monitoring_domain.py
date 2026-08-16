import functools
from json import dumps, loads
from uuid import uuid4

from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops

from bifrostnms.models.monitoring import ProbeType


class Migration(migrations.Migration):
    dependencies = [("models", "0005_enable_timescaledb")]

    initial = False

    operations = [
        ops.CreateModel(
            name="Agent",
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
                ("name", fields.CharField(max_length=200)),
                ("description", fields.TextField(null=True, unique=False)),
                ("enabled", fields.BooleanField(default=True)),
                (
                    "archived_at",
                    fields.DatetimeField(
                        null=True, db_index=True, auto_now=False, auto_now_add=False
                    ),
                ),
            ],
            options={
                "table": "agent",
                "app": "models",
                "unique_together": (("realm", "name"),),
                "pk_attr": "id",
            },
            bases=["RealmOwnedModel"],
        ),
        ops.CreateModel(
            name="AgentConfigurationSnapshot",
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
                (
                    "agent",
                    fields.ForeignKeyField(
                        "models.Agent",
                        source_field="agent_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="configuration_snapshots",
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                ("revision", fields.BigIntField()),
                ("content_hash", fields.CharField(max_length=64)),
                (
                    "configuration",
                    fields.JSONField(
                        encoder=functools.partial(dumps, separators=(",", ":")), decoder=loads
                    ),
                ),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={
                "table": "agentconfigurationsnapshot",
                "app": "models",
                "unique_together": (("realm", "agent", "revision"),),
                "pk_attr": "id",
            },
            bases=["Model"],
        ),
        ops.CreateModel(
            name="AgentConfigurationState",
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
                        related_name="configuration_state",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ("desired_revision", fields.BigIntField(default=0)),
                ("desired_content_hash", fields.CharField(default="", max_length=64)),
                ("acknowledged_revision", fields.BigIntField(default=0)),
                (
                    "acknowledged_at",
                    fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
                ),
            ],
            options={"table": "agentconfigurationstate", "app": "models", "pk_attr": "id"},
            bases=["RealmOwnedModel"],
        ),
        ops.CreateModel(
            name="AgentCredential",
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
                        related_name="credentials",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ("name", fields.CharField(max_length=120)),
                ("credential_hash", fields.CharField(max_length=128)),
                (
                    "last_used_at",
                    fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
                ),
                ("expires_at", fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                (
                    "revoked_at",
                    fields.DatetimeField(
                        null=True, db_index=True, auto_now=False, auto_now_add=False
                    ),
                ),
            ],
            options={
                "table": "agentcredential",
                "app": "models",
                "unique_together": (("realm", "agent", "name"),),
                "pk_attr": "id",
            },
            bases=["RealmOwnedModel"],
        ),
        ops.CreateModel(
            name="AgentGroup",
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
                    "parent",
                    fields.ForeignKeyField(
                        "models.AgentGroup",
                        source_field="parent_id",
                        null=True,
                        db_constraint=True,
                        to_field="id",
                        related_name="children",
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                ("name", fields.CharField(max_length=200)),
                ("description", fields.TextField(null=True, unique=False)),
                ("enabled", fields.BooleanField(default=True)),
                (
                    "archived_at",
                    fields.DatetimeField(
                        null=True, db_index=True, auto_now=False, auto_now_add=False
                    ),
                ),
            ],
            options={"table": "agentgroup", "app": "models", "pk_attr": "id"},
            bases=["RealmOwnedModel"],
        ),
        ops.CreateModel(
            name="AgentGroupMembership",
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
                (
                    "agent_group",
                    fields.ForeignKeyField(
                        "models.AgentGroup",
                        source_field="agent_group_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="memberships",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    "agent",
                    fields.ForeignKeyField(
                        "models.Agent",
                        source_field="agent_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="group_memberships",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={
                "table": "agentgroupmembership",
                "app": "models",
                "unique_together": (("realm", "agent_group", "agent"),),
                "pk_attr": "id",
            },
            bases=["Model"],
        ),
        ops.CreateModel(
            name="Target",
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
                ("name", fields.CharField(max_length=200)),
                ("description", fields.TextField(null=True, unique=False)),
                ("address", fields.CharField(max_length=253)),
                ("enabled", fields.BooleanField(default=True)),
                (
                    "archived_at",
                    fields.DatetimeField(
                        null=True, db_index=True, auto_now=False, auto_now_add=False
                    ),
                ),
            ],
            options={
                "table": "target",
                "app": "models",
                "unique_together": (("realm", "name"),),
                "pk_attr": "id",
            },
            bases=["RealmOwnedModel"],
        ),
        ops.CreateModel(
            name="Monitor",
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
                    "target",
                    fields.ForeignKeyField(
                        "models.Target",
                        source_field="target_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="monitors",
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                ("name", fields.CharField(max_length=200)),
                ("description", fields.TextField(null=True, unique=False)),
                (
                    "probe_type",
                    fields.CharEnumField(
                        description="ICMP: icmp\nHTTP: http\nTCP: tcp\nDNS: dns\nTLS: tls",
                        enum_type=ProbeType,
                        max_length=16,
                    ),
                ),
                ("interval_seconds", fields.IntField()),
                ("timeout_seconds", fields.IntField()),
                (
                    "configuration",
                    fields.JSONField(
                        default=dict,
                        encoder=functools.partial(dumps, separators=(",", ":")),
                        decoder=loads,
                    ),
                ),
                ("enabled", fields.BooleanField(default=True)),
                ("revision", fields.IntField(default=1)),
                (
                    "archived_at",
                    fields.DatetimeField(
                        null=True, db_index=True, auto_now=False, auto_now_add=False
                    ),
                ),
            ],
            options={
                "table": "monitor",
                "app": "models",
                "unique_together": (("realm", "name"),),
                "pk_attr": "id",
            },
            bases=["RealmOwnedModel"],
        ),
        ops.CreateModel(
            name="MonitorAgentAssignment",
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
                    "monitor",
                    fields.ForeignKeyField(
                        "models.Monitor",
                        source_field="monitor_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="agent_assignments",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    "agent",
                    fields.ForeignKeyField(
                        "models.Agent",
                        source_field="agent_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="monitor_assignments",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ("enabled", fields.BooleanField(default=True)),
            ],
            options={
                "table": "monitoragentassignment",
                "app": "models",
                "unique_together": (("realm", "monitor", "agent"),),
                "pk_attr": "id",
            },
            bases=["RealmOwnedModel"],
        ),
        ops.CreateModel(
            name="MonitorAgentGroupAssignment",
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
                    "monitor",
                    fields.ForeignKeyField(
                        "models.Monitor",
                        source_field="monitor_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="agent_group_assignments",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    "agent_group",
                    fields.ForeignKeyField(
                        "models.AgentGroup",
                        source_field="agent_group_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="monitor_assignments",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ("enabled", fields.BooleanField(default=True)),
            ],
            options={
                "table": "monitoragentgroupassignment",
                "app": "models",
                "unique_together": (("realm", "monitor", "agent_group"),),
                "pk_attr": "id",
            },
            bases=["RealmOwnedModel"],
        ),
        ops.CreateModel(
            name="TargetGroup",
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
                    "parent",
                    fields.ForeignKeyField(
                        "models.TargetGroup",
                        source_field="parent_id",
                        null=True,
                        db_constraint=True,
                        to_field="id",
                        related_name="children",
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                ("name", fields.CharField(max_length=200)),
                ("description", fields.TextField(null=True, unique=False)),
                (
                    "archived_at",
                    fields.DatetimeField(
                        null=True, db_index=True, auto_now=False, auto_now_add=False
                    ),
                ),
            ],
            options={"table": "targetgroup", "app": "models", "pk_attr": "id"},
            bases=["RealmOwnedModel"],
        ),
        ops.CreateModel(
            name="TargetGroupMembership",
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
                (
                    "target_group",
                    fields.ForeignKeyField(
                        "models.TargetGroup",
                        source_field="target_group_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="memberships",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    "target",
                    fields.ForeignKeyField(
                        "models.Target",
                        source_field="target_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="group_memberships",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={
                "table": "targetgroupmembership",
                "app": "models",
                "unique_together": (("realm", "target_group", "target"),),
                "pk_attr": "id",
            },
            bases=["Model"],
        ),
        ops.RunSQL(
            """
            CREATE UNIQUE INDEX agentgroup_realm_parent_name_uniq
            ON agentgroup (realm_id, parent_id, name) NULLS NOT DISTINCT;
            CREATE UNIQUE INDEX targetgroup_realm_parent_name_uniq
            ON targetgroup (realm_id, parent_id, name) NULLS NOT DISTINCT;

            ALTER TABLE agentgroup
                ADD CONSTRAINT agentgroup_parent_not_self
                CHECK (parent_id IS NULL OR parent_id <> id);
            ALTER TABLE targetgroup
                ADD CONSTRAINT targetgroup_parent_not_self
                CHECK (parent_id IS NULL OR parent_id <> id);
            ALTER TABLE monitor
                ADD CONSTRAINT monitor_probe_type_valid
                CHECK (probe_type IN ('icmp', 'http', 'tcp', 'dns', 'tls')),
                ADD CONSTRAINT monitor_interval_valid
                CHECK (interval_seconds >= 1),
                ADD CONSTRAINT monitor_timeout_valid
                CHECK (timeout_seconds >= 1 AND timeout_seconds < interval_seconds),
                ADD CONSTRAINT monitor_revision_positive
                CHECK (revision > 0);
            ALTER TABLE agentconfigurationstate
                ADD CONSTRAINT agent_config_revisions_valid
                CHECK (
                    desired_revision >= 0
                    AND acknowledged_revision >= 0
                    AND acknowledged_revision <= desired_revision
                );
            ALTER TABLE agentconfigurationsnapshot
                ADD CONSTRAINT agent_config_snapshot_revision_positive
                CHECK (revision > 0);
            """,
            reverse_sql="""
            ALTER TABLE agentconfigurationsnapshot
                DROP CONSTRAINT agent_config_snapshot_revision_positive;
            ALTER TABLE agentconfigurationstate
                DROP CONSTRAINT agent_config_revisions_valid;
            ALTER TABLE monitor
                DROP CONSTRAINT monitor_revision_positive,
                DROP CONSTRAINT monitor_timeout_valid,
                DROP CONSTRAINT monitor_interval_valid,
                DROP CONSTRAINT monitor_probe_type_valid;
            ALTER TABLE targetgroup
                DROP CONSTRAINT targetgroup_parent_not_self;
            ALTER TABLE agentgroup
                DROP CONSTRAINT agentgroup_parent_not_self;
            DROP INDEX targetgroup_realm_parent_name_uniq;
            DROP INDEX agentgroup_realm_parent_name_uniq;
            """,
        ),
    ]
