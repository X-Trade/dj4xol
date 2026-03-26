# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0199_restore_city_thumbnails_below_threshold'),
    ]

    operations = [
        migrations.AddField(
            model_name='player',
            name='singular_research_next_field',
            field=models.CharField(
                choices=[('lowest', 'Lowest'), ('same', 'Same')],
                default='lowest',
                max_length=8,
            ),
        ),
    ]
