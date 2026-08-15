from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0001_initial")]

    initial = False

    operations = [
        ops.RenameField(
            model_name="User",
            old_name="is_staff",
            new_name="is_superuser",
        ),
    ]
