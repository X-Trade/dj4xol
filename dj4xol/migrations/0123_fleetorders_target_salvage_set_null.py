from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0122_add_patrol_generated_to_fleetorders'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fleetorders',
            name='target_salvage',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='dj4xol.Salvage',
            ),
        ),
    ]
