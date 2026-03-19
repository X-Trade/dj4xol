from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0185_rename_retro_theme_to_haxxor_and_add_arcade'),
    ]

    operations = [
        migrations.AlterField(
            model_name='account',
            name='theme',
            field=models.CharField(
                choices=[
                    ('classic', 'Classic'),
                    ('lcars', 'LCARS'),
                    ('win95', 'Win95'),
                    ('haxxor', 'Haxxor'),
                    ('retro', 'Retro Arcade'),
                ],
                default='classic',
                max_length=20,
            ),
        ),
    ]
