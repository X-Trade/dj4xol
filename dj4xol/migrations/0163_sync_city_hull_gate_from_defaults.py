from django.db import migrations


def sync_city_hull_gate_from_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0162_sync_race_type_stealth_defaults'),
    ]

    operations = [
        migrations.RunPython(
            sync_city_hull_gate_from_defaults,
            migrations.RunPython.noop,
        ),
    ]
