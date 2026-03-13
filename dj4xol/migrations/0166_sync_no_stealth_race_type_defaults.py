from django.db import migrations


def sync_no_stealth_race_type_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0165_sync_warmonger_stealth_defaults'),
    ]

    operations = [
        migrations.RunPython(
            sync_no_stealth_race_type_defaults,
            migrations.RunPython.noop,
        ),
    ]
