# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0129_auto_20260306_2212'),
    ]

    operations = [
        migrations.AddField(
            model_name='productionorder',
            name='added_by_micromanager',
            field=models.BooleanField(default=False),
        ),
    ]
