from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0187_add_hull_speed_advantage'),
    ]

    operations = [
        migrations.AddField(
            model_name='player',
            name='discovered_ancient_debris',
            field=models.BooleanField(default=False),
        ),
    ]
