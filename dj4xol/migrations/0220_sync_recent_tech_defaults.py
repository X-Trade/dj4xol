from django.db import migrations


def sync_recent_tech_defaults(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0219_sync_recent_tech_defaults'),
    ]

    operations = [
        migrations.RunPython(
            sync_recent_tech_defaults,
            migrations.RunPython.noop,
        ),
    ]
