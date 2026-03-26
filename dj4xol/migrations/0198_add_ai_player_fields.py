# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0197_set_dyson_bp_cost'),
    ]

    operations = [
        migrations.AddField(
            model_name='player',
            name='is_ai',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='player',
            name='ai_module',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='player',
            name='ai_last_checkin_year',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
