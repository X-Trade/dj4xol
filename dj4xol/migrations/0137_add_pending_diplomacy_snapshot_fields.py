from django.db import migrations, models


def backfill_pending_diplomacy(apps, schema_editor):
    Player = apps.get_model('dj4xol', 'Player')
    PlayerDiplomaticStance = apps.get_model('dj4xol', 'PlayerDiplomaticStance')
    Player.objects.all().update(
        pending_default_diplomatic_stance=models.F('default_diplomatic_stance')
    )
    PlayerDiplomaticStance.objects.all().update(
        pending_stance=models.F('stance')
    )


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0136_backfill_existing_diplomacy_hostile'),
    ]

    operations = [
        migrations.AddField(
            model_name='player',
            name='pending_default_diplomatic_stance',
            field=models.CharField(
                choices=[
                    ('HOSTILE', 'Hostile'),
                    ('COLD', 'Cold'),
                    ('NEUTRAL', 'Neutral'),
                    ('WARM', 'Warm'),
                    ('ALLIED', 'Allied'),
                ],
                default='NEUTRAL',
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name='playerdiplomaticstance',
            name='pending_stance',
            field=models.CharField(
                choices=[
                    ('HOSTILE', 'Hostile'),
                    ('COLD', 'Cold'),
                    ('NEUTRAL', 'Neutral'),
                    ('WARM', 'Warm'),
                    ('ALLIED', 'Allied'),
                ],
                default='NEUTRAL',
                max_length=8,
            ),
        ),
        migrations.RunPython(backfill_pending_diplomacy, migrations.RunPython.noop),
    ]
