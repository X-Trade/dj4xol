# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0200_add_player_singular_next_field_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='last_turn_execution_seconds',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
