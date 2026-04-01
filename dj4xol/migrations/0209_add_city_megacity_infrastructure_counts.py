# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0208_sync_recent_tech_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='star',
            name='cities',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='star',
            name='megacities',
            field=models.IntegerField(default=0),
        ),
    ]
