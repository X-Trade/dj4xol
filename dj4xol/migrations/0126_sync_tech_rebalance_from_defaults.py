# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import uuid

from django.db import migrations


def _load_defaults_rows():
    import yaml

    fixtures_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'fixtures',
        'defaults.yaml',
    )
    with open(fixtures_path, 'r') as handle:
        return yaml.safe_load(handle) or []


def sync_tech_rebalance_from_defaults(apps, schema_editor):
    # Superseded by later canonical defaults sync migrations.
    return


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0125_auto_20260306_1640'),
    ]

    operations = [
        migrations.RunPython(
            sync_tech_rebalance_from_defaults,
            migrations.RunPython.noop,
        ),
    ]
