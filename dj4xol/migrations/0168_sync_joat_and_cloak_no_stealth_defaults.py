from django.db import migrations


def sync_joat_and_cloak_no_stealth_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0167_replace_has_stealth_with_has_no_stealth'),
    ]

    operations = [
        migrations.RunPython(
            sync_joat_and_cloak_no_stealth_defaults,
            migrations.RunPython.noop,
        ),
    ]
