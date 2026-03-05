# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


BASE_TOTALS = {
    19: 50,
    20: 75,
    21: 100,
    22: 150,
    23: 225,
    24: 325,
    25: 450,
    26: 600,
}


EARLY_SINGLE_WEIGHTS = {
    'METAPHYSICS': {'resource_z': 1},
    'MATERIALS': {'resource_x': 1},
}


COMBO_WEIGHTS = {
    'ENERGY': {'resource_x': 1},
    'ELECTRONICS': {'resource_y': 1},
    'METAPHYSICS': {'resource_z': 1},
    'MATERIALS': {'resource_x': 1, 'resource_y': 2},
    'CONSTRUCTION': {'resource_x': 2, 'resource_z': 1},
}


def _total_for_level(level):
    base = int(BASE_TOTALS.get(level, 0))
    if base <= 0:
        return 0
    if level <= 21:
        multiplier = 2.0
    else:
        multiplier = 2.0 + ((float(level) - 21.0) * (18.0 / 5.0))
    total = int(round(float(base) * multiplier))
    if total >= 10:
        total = (total // 10) * 10
    return max(0, total)


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


def apply_secret_resource_requirements(apps, schema_editor):
    ResearchCategory = apps.get_model('dj4xol', 'ResearchCategory')
    DefaultReq = apps.get_model('dj4xol', 'DefaultResearchLevelRequirement')
    CategoryReq = apps.get_model('dj4xol', 'ResearchLevelRequirement')

    categories = {
        row.code: row
        for row in ResearchCategory.objects.filter(
            code__in=COMBO_WEIGHTS.keys()
        )
    }

    for code, category in categories.items():
        for level in sorted(BASE_TOTALS.keys()):
            total = _total_for_level(level)
            if total <= 0:
                continue
            weights = None
            if level <= 21 and code in EARLY_SINGLE_WEIGHTS:
                weights = EARLY_SINGLE_WEIGHTS[code]
            elif level >= 21:
                weights = COMBO_WEIGHTS.get(code)
            if not weights:
                continue
            allocations = _allocate_costs(total, weights)
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
            req.resource_x_cost = int(allocations.get('resource_x', 0))
            req.resource_y_cost = int(allocations.get('resource_y', 0))
            req.resource_z_cost = int(allocations.get('resource_z', 0))
            req.save(update_fields=[
                'resource_x_cost', 'resource_y_cost', 'resource_z_cost'
            ])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0109_add_secret_resources'),
    ]

    operations = [
        migrations.RunPython(
            apply_secret_resource_requirements,
            migrations.RunPython.noop,
        ),
    ]
