# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0077_sync_tech_tree_from_fixtures_refresh'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleetorders',
            name='bomb_until',
            field=models.CharField(choices=[('COLONISTS_ZERO', 'Until Zero Colonists'), ('DEFENSES_ZERO', 'Until Zero Defenses'), ('CONTINUOUS', 'Continuous')], default='COLONISTS_ZERO', max_length=20),
        ),
        migrations.AddField(
            model_name='fleetorders',
            name='mine_until_full',
            field=models.BooleanField(default=True),
        ),
    ]
