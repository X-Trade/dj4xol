from django.db import migrations


def sync_mechanical_growth_multiplier_from_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0156_add_population_cap_multiplier'),
    ]

    operations = [
        migrations.RunPython(
            sync_mechanical_growth_multiplier_from_defaults,
            migrations.RunPython.noop,
        ),
    ]
