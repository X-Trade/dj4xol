from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('dj4xol', '0115_add_star_thumbnail_path'),
    ]

    operations = [
        migrations.AddField(
            model_name='salvage',
            name='salvage_type',
            field=models.CharField(
                choices=[('SALVAGE', 'Salvage'), ('ASTEROID_FIELD', 'Asteroid Field')],
                default='SALVAGE',
                max_length=24,
            ),
        ),
    ]
