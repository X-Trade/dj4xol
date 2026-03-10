# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def sync_administration_level1_electronics_l7(apps, schema_editor):
    # Superseded by later canonical defaults sync migrations.
    return


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0132_sync_administration_costs_from_defaults'),
    ]

    operations = [
        migrations.RunPython(
            sync_administration_level1_electronics_l7,
            migrations.RunPython.noop,
        ),
    ]
