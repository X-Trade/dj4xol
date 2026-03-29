# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json

from django.db import migrations


def _safe_params(params_json):
    try:
        data = json.loads(params_json or '{}')
        if isinstance(data, dict):
            return data
    except (TypeError, ValueError):
        pass
    return {}


def restrict_prototype_cloak_for_war_and_sci(apps, schema_editor):
    Technology = apps.get_model('dj4xol', 'Technology')
    prototype_cloak = Technology.objects.filter(short_id='tech00000806').first()
    if prototype_cloak is None:
        return
    params = _safe_params(getattr(prototype_cloak, 'params_json', '{}'))
    params['race_type'] = 'has has_no_stealth == False, and is not WAR, and is not SCI'
    prototype_cloak.params_json = json.dumps(params, sort_keys=True)
    prototype_cloak.save(update_fields=['params_json'])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0206_rebalance_bombs_and_mini_cloak'),
    ]

    operations = [
        migrations.RunPython(
            restrict_prototype_cloak_for_war_and_sci,
            migrations.RunPython.noop,
        ),
    ]
