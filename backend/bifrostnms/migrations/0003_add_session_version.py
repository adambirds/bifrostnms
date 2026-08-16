from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0002_rename_is_staff_to_is_superuser")]

    initial = False

    operations = [
        ops.AddField(
            model_name="User",
            name="session_version",
            field=fields.IntField(null=True),
        ),
        ops.RunSQL(
            'UPDATE "user" SET "session_version" = 1 WHERE "session_version" IS NULL',
        ),
        ops.AlterField(
            model_name="User",
            name="session_version",
            field=fields.IntField(default=1),
        ),
    ]
