# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0133_sync_administration_level1_electronics_l7'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleet',
            name='travel_warp',
            field=models.IntegerField(default=0),
        ),
    ]
