from django.db import migrations


def sync_warmonger_stealth_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0164_sync_nonstealth_cloak_gate_from_defaults'),
    ]

    operations = [
        migrations.RunPython(
            sync_warmonger_stealth_defaults,
            migrations.RunPython.noop,
        ),
    ]
