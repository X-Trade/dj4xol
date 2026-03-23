# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def sync_administration_l1_l4_costs(apps, schema_editor):
    Technology = apps.get_model('dj4xol', 'Technology')

    targets = [
        {
            'id': '00000000-0000-0000-0000-000000000411',
            'short_id': 'tech00000411',
            'name': 'Administration Level 1',
            'level': 7,
            'params_json': (
                '{"administration_level": 1, "production_cost_overrides": '
                '{"BUILD_ADMINISTRATION": {"bp": 120, "ironium": 350, '
                '"boranium": 0, "germanium": 250, "colonists": 0}}}'
            ),
        },
        {
            'id': '00000000-0000-0000-0000-000000000414',
            'short_id': 'tech00000414',
            'name': 'Administration Level 4',
            'level': 23,
            'params_json': (
                '{"administration_level": 4, "production_cost_overrides": '
                '{"BUILD_ADMINISTRATION": {"bp": 60, "ironium": 100, '
                '"boranium": 0, "germanium": 260, "colonists": 0}}}'
            ),
        },
    ]

    for target in targets:
        technology = Technology.objects.filter(id=target['id']).first()
        if technology is None:
            technology = Technology.objects.filter(short_id=target['short_id']).first()
        if technology is None:
            technology = Technology.objects.filter(
                name=target['name'],
                level=target['level'],
            ).first()
        if technology is None:
            continue
        if technology.params_json == target['params_json']:
            continue
        technology.params_json = target['params_json']
        technology.save(update_fields=['params_json'])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0191_add_administration_level4_electronics_l23'),
    ]

    operations = [
        migrations.RunPython(
            sync_administration_l1_l4_costs,
            migrations.RunPython.noop,
        ),
    ]

