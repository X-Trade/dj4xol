# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def sync_administration_costs_from_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0131_add_remove_administration_order_type'),
    ]

    operations = [
        migrations.RunPython(
            sync_administration_costs_from_defaults,
            migrations.RunPython.noop,
        ),
    ]
