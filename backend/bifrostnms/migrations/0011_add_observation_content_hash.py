from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0010_add_acknowledged_configuration_hash")]

    initial = False

    operations = [
        ops.RunSQL(
            """
            ALTER TABLE observations
                ADD COLUMN canonical_payload_hash VARCHAR(64);
            """,
            reverse_sql="""
            ALTER TABLE observations DROP COLUMN canonical_payload_hash;
            """,
        )
    ]
