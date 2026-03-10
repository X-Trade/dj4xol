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
        data = yaml.safe_load(handle) or []
    return data


def sync_tech_tree_wormhole_drive(apps, schema_editor):
    # Superseded by later canonical defaults sync migrations.
    return


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0080_allow_wormhole_warpfactor'),
    ]

    operations = [
        migrations.RunPython(
            sync_tech_tree_wormhole_drive,
            migrations.RunPython.noop,
        ),
    ]
