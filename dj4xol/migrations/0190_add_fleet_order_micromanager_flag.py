from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0189_auto_20260320_1322'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleetorders',
            name='added_by_micromanager',
            field=models.BooleanField(default=False),
        ),
    ]

