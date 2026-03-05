from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('dj4xol', '0112_add_level26_all_mineral_surcharge'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleetorders',
            name='remotemine_focus',
            field=models.TextField(blank=True, default=''),
        ),
    ]
