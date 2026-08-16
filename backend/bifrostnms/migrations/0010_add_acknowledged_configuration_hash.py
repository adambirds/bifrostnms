from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0009_add_agent_operational_state")]

    initial = False

    operations = [
        ops.AddField(
            model_name="AgentConfigurationState",
            name="acknowledged_content_hash",
            field=fields.CharField(default="", max_length=64),
        ),
    ]
