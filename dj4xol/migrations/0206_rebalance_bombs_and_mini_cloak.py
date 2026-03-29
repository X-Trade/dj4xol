# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def rebalance_bombs_and_mini_cloak(apps, schema_editor):
    # Superseded by canonical fixture sync migrations.
    return


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0205_backfill_research_technology_grants'),
    ]

    operations = [
        migrations.RunPython(
            rebalance_bombs_and_mini_cloak,
            migrations.RunPython.noop,
        ),
    ]
