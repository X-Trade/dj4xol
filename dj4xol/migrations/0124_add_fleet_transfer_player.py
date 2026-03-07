from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0123_fleetorders_target_salvage_set_null'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleetorders',
            name='transfer_player',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='dj4xol.Player',
            ),
        ),
    ]
