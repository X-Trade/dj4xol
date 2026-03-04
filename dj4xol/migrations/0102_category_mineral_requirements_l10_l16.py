# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
import os

from django.db import migrations, models


CATEGORY_TOTALS = {
    'CONSTRUCTION': {
        6: 100,
        8: 200,
        10: 400,
        11: 1000,
        12: 1500,
        13: 1600,
        14: 2200,
        15: 2800,
        16: 3600,
    },
    'METAPHYSICS': {
        6: 100,
        8: 200,
        10: 400,
        11: 800,
        12: 1200,
        13: 1600,
        14: 2200,
        15: 2800,
        16: 3600,
    },
    'ELECTRONICS': {
        6: 100,
        8: 200,
        10: 300,
        11: 600,
        12: 900,
        13: 1200,
        14: 1600,
        15: 2000,
        16: 2600,
    },
    'MATERIALS': {
        6: 100,
        8: 200,
        10: 600,
        11: 900,
        12: 1200,
        13: 1500,
        14: 2000,
        15: 2600,
        16: 3200,
    },
    'ENERGY': {
        6: 100,
        8: 200,
        10: 300,
        11: 600,
        12: 900,
        13: 1200,
        14: 1600,
        15: 2000,
        16: 2600,
    },
}


RESOURCE_FIELDS = {
    'IRONIUM': 'ironium_cost',
    'BORANIUM': 'boranium_cost',
    'GERMANIUM': 'germanium_cost',
}


FALLBACK_KEY_RESOURCES = {
    'CONSTRUCTION': {'IRONIUM': 1},
    'ENERGY': {'BORANIUM': 1},
    'ELECTRONICS': {'GERMANIUM': 1},
    'MATERIALS': {'IRONIUM': 1, 'BORANIUM': 2},
    'METAPHYSICS': {'BORANIUM': 1, 'GERMANIUM': 1},
}


def _parse_key_resources(category):
    try:
        raw = getattr(category, 'metadata_json', None)
    except Exception:
        raw = None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    key_resources = data.get('key_resources')
    if isinstance(key_resources, dict):
        weights = {
            name: float(weight)
            for name, weight in key_resources.items()
            if name in RESOURCE_FIELDS
        }
    elif isinstance(key_resources, (list, tuple)):
        weights = {
            name: 1.0
            for name in key_resources
            if name in RESOURCE_FIELDS
        }
    else:
        return None
    if not weights:
        return None
    return weights


def _allocate_costs(total, weights):
    items = sorted(weights.items(), key=lambda item: (item[1], item[0]))
    weight_total = sum(weight for _, weight in items)
    if weight_total <= 0:
        return {}
    allocations = {}
    remaining = int(total)
    for name, weight in items[:-1]:
        share = int(float(total) * weight / weight_total)
        if share >= 10:
            share = (share // 10) * 10
        if share > remaining:
            share = remaining
        allocations[name] = share
        remaining -= share
    allocations[items[-1][0]] = remaining
    return allocations


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


def _sync_category_metadata(ResearchCategory):
    rows = _load_defaults_rows()
    for row in rows:
        if row.get('model') != 'dj4xol.ResearchCategory':
            continue
        fields = dict(row.get('fields') or {})
        pk = row.get('pk')
        if pk is None:
            continue
        metadata_json = fields.get('metadata_json')
        if metadata_json is None:
            continue
        ResearchCategory.objects.filter(id=int(pk)).update(
            metadata_json=metadata_json
        )


def apply_category_mineral_requirements(apps, schema_editor):
    ResearchCategory = apps.get_model('dj4xol', 'ResearchCategory')
    DefaultReq = apps.get_model('dj4xol', 'DefaultResearchLevelRequirement')
    CategoryReq = apps.get_model('dj4xol', 'ResearchLevelRequirement')

    _sync_category_metadata(ResearchCategory)

    categories = {
        row.code: row
        for row in ResearchCategory.objects.filter(
            code__in=CATEGORY_TOTALS.keys()
        )
    }

    for code, level_costs in CATEGORY_TOTALS.items():
        category = categories.get(code)
        if not category:
            continue
        weights = _parse_key_resources(category) or FALLBACK_KEY_RESOURCES.get(code)
        if not weights:
            continue
        for level, total in level_costs.items():
            allocations = _allocate_costs(total, weights)
            ironium_cost = allocations.get('IRONIUM', 0)
            boranium_cost = allocations.get('BORANIUM', 0)
            germanium_cost = allocations.get('GERMANIUM', 0)
            req = CategoryReq.objects.filter(
                category=category, level=level
            ).first()
            if not req:
                default = DefaultReq.objects.filter(level=level).first()
                req = CategoryReq(
                    category=category,
                    level=level,
                    rp_cost=int(default.rp_cost) if default else 0,
                    ironium_cost=0,
                    boranium_cost=0,
                    germanium_cost=0,
                )
                req.save()
            req.ironium_cost = int(ironium_cost)
            req.boranium_cost = int(boranium_cost)
            req.germanium_cost = int(germanium_cost)
            req.save(update_fields=[
                'ironium_cost', 'boranium_cost', 'germanium_cost'
            ])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0101_sync_tech_tree_from_fixtures_refresh'),
    ]

    operations = [
        migrations.AddField(
            model_name='researchcategory',
            name='metadata_json',
            field=models.TextField(default='{}'),
        ),
        migrations.RunPython(
            apply_category_mineral_requirements,
            migrations.RunPython.noop,
        ),
    ]
