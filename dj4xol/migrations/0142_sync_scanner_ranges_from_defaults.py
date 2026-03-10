# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def sync_scanner_ranges_from_defaults(apps, schema_editor):
    # Superseded by later canonical defaults sync migrations.
    return


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
