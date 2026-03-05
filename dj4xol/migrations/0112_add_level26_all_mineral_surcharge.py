# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def add_level26_all_mineral_surcharge(apps, schema_editor):
    ResearchCategory = apps.get_model('dj4xol', 'ResearchCategory')
    DefaultReq = apps.get_model('dj4xol', 'DefaultResearchLevelRequirement')
    CategoryReq = apps.get_model('dj4xol', 'ResearchLevelRequirement')

    categories = list(
        ResearchCategory.objects.filter(
            code__in=['ENERGY', 'ELECTRONICS', 'MATERIALS', 'METAPHYSICS', 'CONSTRUCTION']
        )
    )

    for category in categories:
        req = CategoryReq.objects.filter(category=category, level=26).first()
        if not req:
            default = DefaultReq.objects.filter(level=26).first()
            req = CategoryReq(
                category=category,
                level=26,
                rp_cost=int(default.rp_cost) if default else 0,
                ironium_cost=0,
                boranium_cost=0,
                germanium_cost=0,
                resource_x_cost=0,
                resource_y_cost=0,
                resource_z_cost=0,
            )
            req.save()

        req.ironium_cost = int(req.ironium_cost or 0) + 100
        req.boranium_cost = int(req.boranium_cost or 0) + 100
        req.germanium_cost = int(req.germanium_cost or 0) + 100
        req.resource_x_cost = int(req.resource_x_cost or 0) + 100
        req.resource_y_cost = int(req.resource_y_cost or 0) + 100
        req.resource_z_cost = int(req.resource_z_cost or 0) + 100
        req.save(update_fields=[
            'ironium_cost',
            'boranium_cost',
            'germanium_cost',
            'resource_x_cost',
            'resource_y_cost',
            'resource_z_cost',
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0111_adjust_post_l16_mineral_requirements'),
    ]

    operations = [
        migrations.RunPython(
            add_level26_all_mineral_surcharge,
            migrations.RunPython.noop,
        ),
    ]
