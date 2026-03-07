# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0130_add_production_order_micromanager_flag'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productionorder',
            name='order_type',
            field=models.CharField(
                max_length=24,
                choices=[
                    ('TERRAFORM_GRAVITY', 'Terraform Gravity (1%)'),
                    ('TERRAFORM_TEMPERATURE', 'Terraform Temperature (1%)'),
                    ('TERRAFORM_RADIATION', 'Terraform Radiation (1%)'),
                    ('BUILD_FLEET', 'Build Fleet'),
                    ('BUILD_MINE', 'Build Mine'),
                    ('BUILD_FACTORY', 'Build Factory'),
                    ('BUILD_LAB', 'Build Lab'),
                    ('BUILD_DEFENSE', 'Build Defense'),
                    ('BUILD_SHIPYARD', 'Build Shipyard'),
                    ('BUILD_ADMINISTRATION', 'Build Administration'),
                    ('REMOVE_ADMINISTRATION', 'Remove Administration'),
                ],
            ),
        ),
    ]
