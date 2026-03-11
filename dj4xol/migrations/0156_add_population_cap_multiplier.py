from django.db import migrations, models


def sync_race_type_population_cap_multiplier_from_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0155_backfill_salvage_danger_levels'),
    ]

    operations = [
        migrations.AddField(
            model_name='serverracetype',
            name='population_cap_multiplier',
            field=models.IntegerField(default=1),
        ),
        migrations.RunPython(
            sync_race_type_population_cap_multiplier_from_defaults,
            migrations.RunPython.noop,
        ),
    ]
