# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def restrict_prototype_cloak_for_war_and_sci(apps, schema_editor):
    # Superseded by canonical fixture sync migrations.
    return


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0206_rebalance_bombs_and_mini_cloak'),
    ]

    operations = [
        migrations.RunPython(
            restrict_prototype_cloak_for_war_and_sci,
            migrations.RunPython.noop,
        ),
    ]
