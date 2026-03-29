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


def rebalance_bombs_and_mini_cloak(apps, schema_editor):
    ResearchCategory = apps.get_model('dj4xol', 'ResearchCategory')
    Technology = apps.get_model('dj4xol', 'Technology')

    energy = ResearchCategory.objects.filter(code='ENERGY').first()
    energy_id = getattr(energy, 'id', None)

    nova = Technology.objects.filter(short_id='tech00000605').first()
    if nova is not None:
        nova.level = 21
        if energy_id is not None:
            nova.category_id = energy_id
        nova.save(update_fields=['category', 'level'] if energy_id is not None else ['level'])

    supernova = Technology.objects.filter(short_id='tech00000606').first()
    if supernova is not None:
        supernova.level = 26
        if energy_id is not None:
            supernova.category_id = energy_id
        supernova.save(update_fields=['category', 'level'] if energy_id is not None else ['level'])

    mini_cloak = Technology.objects.filter(short_id='tech00000801').first()
    if mini_cloak is not None:
        params = _safe_params(getattr(mini_cloak, 'params_json', '{}'))
        params['max_cloaked_warp'] = 3
        params['race_type'] = 'is SCI, is WAR'
        mini_cloak.params_json = json.dumps(params, sort_keys=True)
        mini_cloak.save(update_fields=['params_json'])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0205_backfill_research_technology_grants'),
    ]

    operations = [
        migrations.RunPython(
            rebalance_bombs_and_mini_cloak,
            migrations.RunPython.noop,
        ),
    ]
