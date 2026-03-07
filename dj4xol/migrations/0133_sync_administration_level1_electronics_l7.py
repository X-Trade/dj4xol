# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def sync_administration_level1_electronics_l7(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


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
