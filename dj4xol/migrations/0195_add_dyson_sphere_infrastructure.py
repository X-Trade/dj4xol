# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import uuid

from django.db import migrations, models


def add_dyson_sphere_technology(apps, schema_editor):
    ResearchCategory = apps.get_model('dj4xol', 'ResearchCategory')
    Technology = apps.get_model('dj4xol', 'Technology')

    construction = ResearchCategory.objects.filter(code='CONSTRUCTION').first()
    if construction is None:
        return

    tech_id = uuid.UUID('00000000-0000-0000-0000-000000000415')
    short_id = 'tech00000415'
    name = 'Dyson Sphere'
    fields = {
        'short_id': short_id,
        'category_id': construction.id,
        'level': 24,
        'name': name,
        'description': (
            'Megastructure engineering enables one Dyson Sphere per colony, '
            'vastly accelerating local industry and research.'
        ),
        'tech_type': 'INFRASTRUCTURE',
        'params_json': (
            '{"dyson_sphere": true, "production_cost_overrides": '
            '{"BUILD_DYSON_SPHERE": {"bp": 0, "ironium": 1000, '
            '"boranium": 500, "germanium": 600, "resource_x": 200, '
            '"resource_y": 0, "resource_z": 100, "colonists": 0}}}'
        ),
        'display_order': 214,
        'enabled': True,
    }

    technology = Technology.objects.filter(id=tech_id).first()
    if technology is None:
        technology = Technology.objects.filter(short_id=short_id).first()
    if technology is None:
        technology = Technology.objects.filter(
            category_id=construction.id,
            level=24,
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
        ('dj4xol', '0194_account_email_html_enabled'),
    ]

    operations = [
        migrations.AddField(
            model_name='star',
            name='has_dyson_sphere',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='productionorder',
            name='order_type',
            field=models.CharField(
                choices=[
                    ('TERRAFORM_GRAVITY', 'Terraform Gravity (1%)'),
                    ('TERRAFORM_TEMPERATURE', 'Terraform Temperature (1%)'),
                    ('TERRAFORM_RADIATION', 'Terraform Radiation (1%)'),
                    ('BUILD_FLEET', 'Build Fleet'),
                    ('BUILD_MINE', 'Build Mine'),
                    ('BUILD_FACTORY', 'Build Factory'),
                    ('BUILD_COLONISTS_1K', 'Produce 1k Colonists'),
                    ('BUILD_COLONISTS_1M', 'Produce 1m Colonists'),
                    ('BUILD_LAB', 'Build Lab'),
                    ('BUILD_DEFENSE', 'Build Defense'),
                    ('BUILD_SHIPYARD', 'Build Shipyard'),
                    ('BUILD_ADMINISTRATION', 'Build Administration'),
                    ('REMOVE_ADMINISTRATION', 'Remove Administration'),
                    ('BUILD_DYSON_SPHERE', 'Build Dyson Sphere'),
                ],
                max_length=24,
            ),
        ),
        migrations.RunPython(
            add_dyson_sphere_technology,
            migrations.RunPython.noop,
        ),
    ]
