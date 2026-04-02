from django.db import migrations


def sync_recent_tech_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0222_sync_recent_tech_defaults'),
    ]

    operations = [
        migrations.RunPython(
            sync_recent_tech_defaults,
            migrations.RunPython.noop,
        ),
    ]

