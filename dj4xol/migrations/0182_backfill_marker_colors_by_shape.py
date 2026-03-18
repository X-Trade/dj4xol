from django.db import migrations, models


def backfill_marker_colors(apps, schema_editor):
    PlayerStarMarker = apps.get_model('dj4xol', 'PlayerStarMarker')

    PlayerStarMarker.objects.filter(
        marker_type='X',
    ).filter(
        models.Q(marker_color='WHITE') | models.Q(marker_color='') | models.Q(marker_color__isnull=True)
    ).update(marker_color='RED')

    PlayerStarMarker.objects.filter(
        marker_type='CIRCLE',
    ).filter(
        models.Q(marker_color='WHITE') | models.Q(marker_color='') | models.Q(marker_color__isnull=True)
    ).update(marker_color='BLUE')

    PlayerStarMarker.objects.filter(
        models.Q(marker_color='WHITE') | models.Q(marker_color='') | models.Q(marker_color__isnull=True)
    ).update(marker_color='BLUE')


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0181_add_player_star_marker_color'),
    ]

    operations = [
        migrations.RunPython(backfill_marker_colors, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='playerstarmarker',
            name='marker_color',
            field=models.CharField(
                choices=[
                    ('WHITE', 'White'),
                    ('RED', 'Red'),
                    ('YELLOW', 'Yellow'),
                    ('GREEN', 'Green'),
                    ('BLUE', 'Blue'),
                    ('INDIGO', 'Indigo'),
                    ('VIOLET', 'Violet'),
                ],
                default='BLUE',
                max_length=10,
            ),
        ),
    ]
