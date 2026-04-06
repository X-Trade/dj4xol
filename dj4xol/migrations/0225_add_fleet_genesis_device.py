from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0224_flatten_endgame_research_rp_curve'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleet',
            name='has_genesis_device',
            field=models.BooleanField(default=False),
        ),
    ]
