# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def sync_scanner_ranges_from_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0141_rename_starting_planets_to_starting_colonies'),
    ]

    operations = [
        migrations.RunPython(
            sync_scanner_ranges_from_defaults,
            migrations.RunPython.noop,
        ),
    ]
