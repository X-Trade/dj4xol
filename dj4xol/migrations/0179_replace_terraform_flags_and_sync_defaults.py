from django.db import migrations, models


def backfill_terraform_flags(apps, schema_editor):
    ServerRaceType = apps.get_model('dj4xol', 'ServerRaceType')
    for race_type in ServerRaceType.objects.all():
        had_terraforming = bool(getattr(race_type, 'has_terraforming', True))
        race_type.has_no_terraforming = not had_terraforming
        race_type.only_basic_terraforming = False
        race_type.save(update_fields=[
            'has_no_terraforming',
            'only_basic_terraforming',
        ])


def sync_terraform_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0178_link_hull_designs_to_hull_techs'),
    ]

    operations = [
        migrations.AddField(
            model_name='serverracetype',
            name='has_no_terraforming',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='serverracetype',
            name='only_basic_terraforming',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(
            backfill_terraform_flags,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name='serverracetype',
            name='has_terraforming',
        ),
        migrations.RunPython(
            sync_terraform_defaults,
            migrations.RunPython.noop,
        ),
    ]
