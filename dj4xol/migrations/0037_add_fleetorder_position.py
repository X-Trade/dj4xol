from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0036_add_salvage_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleetorders',
            name='position',
            field=models.IntegerField(default=0),
        ),
    ]
