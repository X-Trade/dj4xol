# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def cap_wormhole_drive_mk3_at_level26(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0143_sync_bomb_and_propulsion_levels_from_defaults'),
    ]

    operations = [
        migrations.RunPython(
            cap_wormhole_drive_mk3_at_level26,
            migrations.RunPython.noop,
        ),
    ]
