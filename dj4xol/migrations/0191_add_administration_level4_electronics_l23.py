# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import uuid

from django.db import migrations


def add_administration_level4_electronics_l23(apps, schema_editor):
    ResearchCategory = apps.get_model('dj4xol', 'ResearchCategory')
    Technology = apps.get_model('dj4xol', 'Technology')

    electronics = ResearchCategory.objects.filter(code='ELECTRONICS').first()
    if electronics is None:
        return

    tech_id = uuid.UUID('00000000-0000-0000-0000-000000000414')
    short_id = 'tech00000414'
    name = 'Administration Level 4'
    fields = {
        'short_id': short_id,
        'category_id': electronics.id,
        'level': 23,
        'name': name,
        'description': (
            'Strategic administrations can coordinate colony logistics and fleet dispatch.'
        ),
        'tech_type': 'INFRASTRUCTURE',
        'params_json': (
            '{"administration_level": 4, "production_cost_overrides": '
            '{"BUILD_ADMINISTRATION": {"bp": 70, "ironium": 175, '
            '"boranium": 0, "germanium": 250, "colonists": 0}}}'
        ),
        'display_order': 213,
        'enabled': True,
    }

    technology = Technology.objects.filter(id=tech_id).first()
    if technology is None:
        technology = Technology.objects.filter(short_id=short_id).first()
    if technology is None:
        technology = Technology.objects.filter(
            category_id=electronics.id,
            level=23,
            name=name,
        ).first()

    if technology is None:
        Technology.objects.create(id=tech_id, **fields)
        return

    for key, value in fields.items():
        setattr(technology, key, value)
    technology.save()


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0190_add_fleet_order_micromanager_flag'),
    ]

    operations = [
        migrations.RunPython(
            add_administration_level4_electronics_l23,
            migrations.RunPython.noop,
        ),
    ]

