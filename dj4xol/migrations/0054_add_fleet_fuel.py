from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0053_rename_propulsion_tech_labels'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleet',
            name='fuel',
            field=models.FloatField(default=50.0),
        ),
        migrations.AddField(
            model_name='fleet',
            name='max_fuel',
            field=models.FloatField(default=50.0),
        ),
    ]
