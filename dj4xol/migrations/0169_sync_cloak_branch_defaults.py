from django.db import migrations


def sync_cloak_branch_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0168_sync_joat_and_cloak_no_stealth_defaults'),
    ]

    operations = [
        migrations.RunPython(
            sync_cloak_branch_defaults,
            migrations.RunPython.noop,
        ),
    ]
