from django.db import migrations, models


def sync_special_cloak_techs_from_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0159_add_race_creation_points_balance'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleet',
            name='advanced_cloak',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='fleet',
            name='max_cloaked_warp',
            field=models.IntegerField(default=-1),
        ),
        migrations.AddField(
            model_name='playerdiplomaticstance',
            name='reveal_cloaked_fleets',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(
            sync_special_cloak_techs_from_defaults,
            migrations.RunPython.noop,
        ),
    ]
