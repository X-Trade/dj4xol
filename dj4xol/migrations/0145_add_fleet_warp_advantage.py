from django.db import migrations, models


def sync_warp_advantage_defaults_and_backfill_fleets(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)

    Fleet = apps.get_model('dj4xol', 'Fleet')
    for fleet in Fleet.objects.filter(player__isnull=False).select_related('player__race_type'):
        player = getattr(fleet, 'player', None)
        race_type = getattr(player, 'race_type', None) if player is not None else None
        try:
            warp_advantage = float(getattr(race_type, 'warp_advantage', 0.0) or 0.0)
        except (TypeError, ValueError):
            warp_advantage = 0.0
        fleet.warp_advantage = warp_advantage
        fleet.save(update_fields=['warp_advantage'])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0144_cap_wormhole_drive_mk3_at_level26'),
    ]

    operations = [
        migrations.RenameField(
            model_name='serverracetype',
            old_name='warp_multiplier',
            new_name='warp_advantage',
        ),
        migrations.AddField(
            model_name='fleet',
            name='warp_advantage',
            field=models.FloatField(default=0.0),
        ),
        migrations.RunPython(
            sync_warp_advantage_defaults_and_backfill_fleets,
            migrations.RunPython.noop,
        ),
    ]
