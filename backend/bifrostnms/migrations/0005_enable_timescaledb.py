from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0004_add_audit_events")]

    initial = False

    operations = [
        ops.RunSQL("CREATE EXTENSION IF NOT EXISTS timescaledb"),
    ]
