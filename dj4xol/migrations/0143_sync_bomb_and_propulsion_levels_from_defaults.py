# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def sync_bomb_and_propulsion_levels_from_defaults(apps, schema_editor):
    # Superseded by later canonical defaults sync migrations.
    return


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0142_sync_scanner_ranges_from_defaults'),
    ]

    operations = [
        migrations.RunPython(
            sync_bomb_and_propulsion_levels_from_defaults,
            migrations.RunPython.noop,
        ),
    ]
