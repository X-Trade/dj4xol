from django.db import migrations


def sync_fuel_factory_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0175_add_fleet_fuel_factory_fields'),
    ]

    operations = [
        migrations.RunPython(
            sync_fuel_factory_defaults,
            migrations.RunPython.noop,
        ),
    ]
