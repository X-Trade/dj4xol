from django.db import migrations


def sync_race_type_stealth_from_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0161_auto_20260312_1155'),
    ]

    operations = [
        migrations.RunPython(
            sync_race_type_stealth_from_defaults,
            migrations.RunPython.noop,
        ),
    ]
