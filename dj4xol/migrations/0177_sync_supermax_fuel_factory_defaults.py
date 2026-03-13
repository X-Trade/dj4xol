from django.db import migrations


def sync_supermax_fuel_factory_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0176_sync_fuel_factory_defaults'),
    ]

    operations = [
        migrations.RunPython(
            sync_supermax_fuel_factory_defaults,
            migrations.RunPython.noop,
        ),
    ]
