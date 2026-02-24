from __future__ import unicode_literals

import json
from django.db import migrations, models


def forward_update_construction_and_infrastructure(apps, schema_editor):
    ResearchCategory = apps.get_model('dj4xol', 'ResearchCategory')
    Technology = apps.get_model('dj4xol', 'Technology')

    # Rename category if an existing INFRASTRUCTURE category is present.
    for category in ResearchCategory.objects.filter(code='INFRASTRUCTURE'):
        category.code = 'CONSTRUCTION'
        category.name = 'Construction'
        category.description = (
            'Planetary installations, civil engineering, and logistics.'
        )
        category.save(update_fields=['code', 'name', 'description'])

    categories_by_code = {
        c.code: c for c in ResearchCategory.objects.filter(
            code__in=[
                'ENERGY', 'ELECTRONICS', 'MATERIALS', 'METAPHYSICS',
                'CONSTRUCTION',
            ]
        )
    }
    short_id_to_category_code = {
        'tech00000401': 'ELECTRONICS',
        'tech00000402': 'ENERGY',
        'tech00000403': 'MATERIALS',
        'tech00000404': 'CONSTRUCTION',
        'tech00000405': 'METAPHYSICS',
        'tech00000406': 'CONSTRUCTION',
    }
    for short_id, category_code in short_id_to_category_code.items():
        category = categories_by_code.get(category_code)
        if category is None:
            continue
        Technology.objects.filter(short_id=short_id).update(category_id=category.id)

    # Move colony defense technologies to INFRASTRUCTURE type.
    for tech in Technology.objects.filter(tech_type='OTHER').iterator():
        try:
            params = json.loads(tech.params_json or '{}')
        except (TypeError, ValueError):
            continue
        if not isinstance(params, dict):
            continue
        if ('colony_defense_level' in params or
                'colony_defence_level' in params):
            tech.tech_type = 'INFRASTRUCTURE'
            tech.save(update_fields=['tech_type'])


def reverse_update_construction_and_infrastructure(apps, schema_editor):
    ResearchCategory = apps.get_model('dj4xol', 'ResearchCategory')
    Technology = apps.get_model('dj4xol', 'Technology')

    for category in ResearchCategory.objects.filter(code='CONSTRUCTION'):
        category.code = 'INFRASTRUCTURE'
        category.name = 'Infrastructure'
        category.description = (
            'Planetary installations, logistics, and colonial defenses.'
        )
        category.save(update_fields=['code', 'name', 'description'])

    infrastructure_category = ResearchCategory.objects.filter(
        code='INFRASTRUCTURE'
    ).first()
    if infrastructure_category is not None:
        Technology.objects.filter(
            short_id__in=[
                'tech00000401',
                'tech00000402',
                'tech00000403',
                'tech00000404',
                'tech00000405',
                'tech00000406',
            ]
        ).update(category_id=infrastructure_category.id)

    for tech in Technology.objects.filter(tech_type='INFRASTRUCTURE').iterator():
        try:
            params = json.loads(tech.params_json or '{}')
        except (TypeError, ValueError):
            continue
        if not isinstance(params, dict):
            continue
        if ('colony_defense_level' in params or
                'colony_defence_level' in params):
            tech.tech_type = 'OTHER'
            tech.save(update_fields=['tech_type'])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0048_update_technology_tech_types'),
    ]

    operations = [
        migrations.AlterField(
            model_name='technology',
            name='tech_type',
            field=models.CharField(
                choices=[
                    ('PROPULSION', 'Propulsion'),
                    ('ENERGY_WEAPON', 'Energy Weapon'),
                    ('TORPEDO', 'Torpedo'),
                    ('SHIELD', 'Shield'),
                    ('ARMOUR', 'Armour'),
                    ('INFRASTRUCTURE', 'Infrastructure'),
                    ('OTHER', 'Other'),
                ],
                default='OTHER',
                max_length=16,
            ),
        ),
        migrations.RunPython(
            forward_update_construction_and_infrastructure,
            reverse_update_construction_and_infrastructure,
        ),
    ]
