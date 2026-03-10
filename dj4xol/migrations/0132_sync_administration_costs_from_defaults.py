# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def sync_administration_costs_from_defaults(apps, schema_editor):
    # Superseded by later canonical defaults sync migrations.
    return


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
