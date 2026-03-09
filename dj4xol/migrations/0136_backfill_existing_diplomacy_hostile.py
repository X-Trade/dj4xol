from django.db import migrations


def backfill_existing_diplomacy_hostile(apps, schema_editor):
    Player = apps.get_model('dj4xol', 'Player')
    PlayerDiplomaticStance = apps.get_model('dj4xol', 'PlayerDiplomaticStance')

    Player.objects.all().update(default_diplomatic_stance='HOSTILE')
    PlayerDiplomaticStance.objects.all().update(stance='HOSTILE')


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0135_add_player_diplomacy'),
    ]

    operations = [
        migrations.RunPython(
            backfill_existing_diplomacy_hostile,
            migrations.RunPython.noop,
        ),
    ]
