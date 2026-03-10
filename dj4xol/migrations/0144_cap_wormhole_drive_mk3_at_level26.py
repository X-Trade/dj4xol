# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def retired_fixture_sync_noop(apps, schema_editor):
    # Retired fixture sync. Fresh installs should only execute the newest
    # canonical defaults sync migration to avoid replaying modern fixtures
    # against historical schemas.
    return None


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0143_sync_bomb_and_propulsion_levels_from_defaults'),
    ]

    operations = [
        migrations.RunPython(
            retired_fixture_sync_noop,
            migrations.RunPython.noop,
        ),
    ]
