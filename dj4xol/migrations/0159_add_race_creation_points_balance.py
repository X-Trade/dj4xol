from django.db import migrations, models


def sync_race_type_points_balance_from_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0158_add_player_star_marker'),
    ]

    operations = [
        migrations.AddField(
            model_name='serverracetype',
            name='race_creation_points_balance',
            field=models.FloatField(default=0.0),
        ),
        migrations.RunPython(
            sync_race_type_points_balance_from_defaults,
            migrations.RunPython.noop,
        ),
    ]
