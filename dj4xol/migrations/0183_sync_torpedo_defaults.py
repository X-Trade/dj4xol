from django.db import migrations


def sync_torpedo_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0182_backfill_marker_colors_by_shape'),
    ]

    operations = [
        migrations.RunPython(
            sync_torpedo_defaults,
            migrations.RunPython.noop,
        ),
    ]
