from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0057_regenerate_unowned_star_minerals'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleet',
            name='fuel_efficiency',
            field=models.FloatField(default=1.0),
        ),
        migrations.AddField(
            model_name='fleet',
            name='overmax_fuel_penalty',
            field=models.FloatField(default=1.0),
        ),
    ]
