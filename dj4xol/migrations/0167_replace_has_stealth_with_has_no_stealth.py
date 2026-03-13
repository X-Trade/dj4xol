from django.db import migrations, models


def backfill_has_no_stealth(apps, schema_editor):
    ServerRaceType = apps.get_model('dj4xol', 'ServerRaceType')
    for race_type in ServerRaceType.objects.all():
        race_type.has_no_stealth = not bool(getattr(race_type, 'has_stealth', False))
        race_type.save(update_fields=['has_no_stealth'])


def sync_has_no_stealth_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0166_sync_no_stealth_race_type_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='serverracetype',
            name='has_no_stealth',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(
            backfill_has_no_stealth,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name='serverracetype',
            name='has_stealth',
        ),
        migrations.RunPython(
            sync_has_no_stealth_defaults,
            migrations.RunPython.noop,
        ),
    ]
