from django.db import migrations


def sync_recent_tech_defaults(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0211_auto_20260401_0959'),
    ]

    operations = [
        migrations.RunPython(
            sync_recent_tech_defaults,
            migrations.RunPython.noop,
        ),
    ]
