# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


def mark_existing_technology_grants_as_diplomatic(apps, schema_editor):
    PlayerTechnologyGrant = apps.get_model('dj4xol', 'PlayerTechnologyGrant')
    PlayerTechnologyGrant.objects.all().update(obtained_via_diplomacy=True)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0203_fix_stale_auto_orders_after_admin_removal'),
    ]

    operations = [
        migrations.AddField(
            model_name='playertechnologygrant',
            name='obtained_via_diplomacy',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(
            mark_existing_technology_grants_as_diplomatic,
            migrations.RunPython.noop,
        ),
    ]
