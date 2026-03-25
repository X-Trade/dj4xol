# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json

from django.db import migrations


DYSON_ORDER_TYPE = 'BUILD_DYSON_SPHERE'
DYSON_BP_COST = 2000


def set_dyson_bp_cost(apps, schema_editor):
    Technology = apps.get_model('dj4xol', 'Technology')

    queryset = Technology.objects.all().only('id', 'name', 'params_json')
    for tech in queryset.iterator():
        raw_params = getattr(tech, 'params_json', None)
        try:
            params = json.loads(raw_params) if raw_params else {}
        except (TypeError, ValueError):
            continue
        if not isinstance(params, dict):
            continue

        overrides = params.get('production_cost_overrides')
        if not isinstance(overrides, dict):
            overrides = {}

        is_dyson = (
            bool(params.get('dyson_sphere')) or
            DYSON_ORDER_TYPE in overrides or
            str(getattr(tech, 'name', '') or '').strip().lower() == 'dyson sphere'
        )
        if not is_dyson:
            continue

        order_cost = overrides.get(DYSON_ORDER_TYPE)
        if not isinstance(order_cost, dict):
            order_cost = {}
        if int(order_cost.get('bp', 0) or 0) == DYSON_BP_COST:
            continue

        order_cost['bp'] = DYSON_BP_COST
        overrides[DYSON_ORDER_TYPE] = order_cost
        params['production_cost_overrides'] = overrides
        tech.params_json = json.dumps(params)
        tech.save(update_fields=['params_json'])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0196_add_technology_thumbnail_fields'),
    ]

    operations = [
        migrations.RunPython(set_dyson_bp_cost, migrations.RunPython.noop),
    ]

