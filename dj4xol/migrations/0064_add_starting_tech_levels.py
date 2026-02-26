from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0063_adjust_probe_hull_capacities'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='max_starting_tech_level',
            field=models.IntegerField(default=5),
        ),
        migrations.AddField(
            model_name='player',
            name='starting_tech_level',
            field=models.IntegerField(default=3),
        ),
        migrations.AddField(
            model_name='serverrace',
            name='starting_tech_level',
            field=models.IntegerField(default=3),
        ),
    ]
