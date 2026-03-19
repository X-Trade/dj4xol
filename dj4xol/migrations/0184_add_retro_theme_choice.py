from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0183_sync_torpedo_defaults'),
    ]

    operations = [
        migrations.AlterField(
            model_name='account',
            name='theme',
            field=models.CharField(
                choices=[
                    ('classic', 'Classic'),
                    ('lcars', 'LCARS'),
                    ('win95', 'Windows 95'),
                    ('retro', 'Retro Arcade'),
                ],
                default='classic',
                max_length=20,
            ),
        ),
    ]
