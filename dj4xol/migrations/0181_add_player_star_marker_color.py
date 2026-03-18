from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0180_add_scanner_hull_slot_type'),
    ]

    operations = [
        migrations.AddField(
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
                default='WHITE',
                max_length=10,
            ),
        ),
    ]
