# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0079_rename_bomb_until_continuous_to_once'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fleetorders',
            name='warpfactor',
            field=models.IntegerField(default=0, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(14)]),
        ),
    ]
