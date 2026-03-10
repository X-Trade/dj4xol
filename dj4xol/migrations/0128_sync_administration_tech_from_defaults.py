# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def sync_administration_tech_from_defaults(apps, schema_editor):
    # Superseded by later canonical defaults sync migrations.
    return


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
