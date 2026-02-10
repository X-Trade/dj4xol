from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0033_add_reports'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleetorders',
            name='patrol_radius',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='fleetorders',
            name='intercept_speed',
            field=models.IntegerField(default=5),
        ),
    ]
