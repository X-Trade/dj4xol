# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json

from django.db import migrations, models


def backfill_technology_thumbnail_fields(apps, schema_editor):
    Technology = apps.get_model('dj4xol', 'Technology')
    queryset = Technology.objects.all().order_by('id')
    for tech in queryset:
        changed = False
        try:
            params = json.loads(getattr(tech, 'params_json', '') or '{}')
        except (TypeError, ValueError):
            params = {}
        if not isinstance(params, dict):
            params = {}

        tech_type = str(getattr(tech, 'tech_type', '') or '').strip().upper()
        class_value = (
            str(params.get('thumbnail_class') or '').strip()
            or str(params.get('thumbnail_cycle') or '').strip()
        )
        raw_hull_class = str(params.get('hull_thumbnail_class') or '').strip().lower()
        if not class_value and tech_type == 'HULL' and raw_hull_class:
            class_value = 'ship/%s' % raw_hull_class
        if class_value and tech_type == 'HULL' and '/' not in class_value:
            class_value = 'ship/%s' % class_value.strip().lower()
        path_value = str(params.get('thumbnail_path') or '').strip()

        if class_value and not str(getattr(tech, 'thumbnail_class', '') or '').strip():
            tech.thumbnail_class = class_value
            changed = True
        if path_value and not str(getattr(tech, 'thumbnail_path', '') or '').strip():
            tech.thumbnail_path = path_value
            changed = True

        if not str(getattr(tech, 'thumbnail_class', '') or '').strip():
            is_dyson = bool(params.get('dyson_sphere'))
            if not is_dyson:
                overrides = params.get('production_cost_overrides')
                is_dyson = (
                    isinstance(overrides, dict)
                    and 'BUILD_DYSON_SPHERE' in overrides
                )
            if not is_dyson:
                name = str(getattr(tech, 'name', '') or '').strip().lower()
                is_dyson = 'dyson sphere' in name
            if is_dyson:
                tech.thumbnail_class = 'star/dyson'
                changed = True

        # Class and path are mutually exclusive; class takes precedence.
        if str(getattr(tech, 'thumbnail_class', '') or '').strip():
            if str(getattr(tech, 'thumbnail_path', '') or '').strip():
                tech.thumbnail_path = ''
                changed = True

        if changed:
            tech.save(update_fields=['thumbnail_class', 'thumbnail_path'])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0195_add_dyson_sphere_infrastructure'),
    ]

    operations = [
        migrations.AddField(
            model_name='technology',
            name='thumbnail_class',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.AddField(
            model_name='technology',
            name='thumbnail_path',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.RunPython(
            backfill_technology_thumbnail_fields,
            migrations.RunPython.noop,
        ),
    ]
