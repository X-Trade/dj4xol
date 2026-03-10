# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def sync_race_type_tech_gates_from_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0145_add_fleet_warp_advantage'),
    ]

    operations = [
        migrations.RunPython(
            sync_race_type_tech_gates_from_defaults,
            migrations.RunPython.noop,
        ),
    ]
