# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def sync_administration_tech_from_defaults(apps, schema_editor):
    from dj4xol.default_sync import sync_factory_defaults

    sync_factory_defaults(force=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0127_add_star_administration'),
    ]

    operations = [
        migrations.RunPython(
            sync_administration_tech_from_defaults,
            migrations.RunPython.noop,
        ),
    ]
