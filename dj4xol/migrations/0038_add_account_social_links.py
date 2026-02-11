from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0037_add_fleetorder_position'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='website_url',
            field=models.URLField(blank=True, default=''),
        ),
    ]
