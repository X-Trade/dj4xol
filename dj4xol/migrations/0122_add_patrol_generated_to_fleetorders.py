from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0121_add_player_note'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleetorders',
            name='patrol_generated',
            field=models.BooleanField(default=False),
        ),
    ]
