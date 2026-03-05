# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


CATEGORY_TOTALS = {
    'ENERGY': {
        17: 3800,
        18: 4200,
        19: 4600,
        20: 5000,
        21: 3200,
        22: 2200,
        23: 1500,
        24: 900,
        25: 500,
    },
    'ELECTRONICS': {
        17: 3600,
        18: 4100,
        19: 4500,
        20: 4900,
        21: 3100,
        22: 2100,
        23: 1400,
        24: 800,
        25: 500,
    },
    'MATERIALS': {
        17: 3900,
        18: 4400,
        19: 4700,
        20: 5000,
        21: 3300,
        22: 2300,
        23: 1600,
        24: 950,
        25: 500,
    },
    'METAPHYSICS': {
        17: 4000,
        18: 4500,
        19: 4800,
        20: 5000,
        21: 3400,
        22: 2400,
        23: 1700,
        24: 1000,
        25: 500,
    },
    'CONSTRUCTION': {
        17: 3800,
        18: 4300,
        19: 4600,
        20: 5000,
        21: 3200,
        22: 2200,
        23: 1500,
        24: 900,
        25: 500,
    },
}


RESOURCE_FIELDS = {
    'IRONIUM': 'ironium_cost',
    'BORANIUM': 'boranium_cost',
    'GERMANIUM': 'germanium_cost',
}


CATEGORY_WEIGHTS = {
    'ENERGY': {'BORANIUM': 3, 'IRONIUM': 1},
    'ELECTRONICS': {'GERMANIUM': 3, 'BORANIUM': 1},
    'MATERIALS': {'BORANIUM': 3, 'IRONIUM': 2, 'GERMANIUM': 1},
    'METAPHYSICS': {'GERMANIUM': 3, 'BORANIUM': 2, 'IRONIUM': 1},
    'CONSTRUCTION': {'IRONIUM': 3, 'BORANIUM': 1},
}


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


def apply_post_l16_mineral_requirements(apps, schema_editor):
    ResearchCategory = apps.get_model('dj4xol', 'ResearchCategory')
    DefaultReq = apps.get_model('dj4xol', 'DefaultResearchLevelRequirement')
    CategoryReq = apps.get_model('dj4xol', 'ResearchLevelRequirement')

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
        weights = CATEGORY_WEIGHTS.get(code)
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
        ('dj4xol', '0110_secret_resource_requirements_l19_l26'),
    ]

    operations = [
        migrations.RunPython(
            apply_post_l16_mineral_requirements,
            migrations.RunPython.noop,
        ),
    ]
