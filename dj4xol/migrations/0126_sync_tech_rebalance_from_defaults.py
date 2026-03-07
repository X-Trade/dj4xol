# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import uuid

from django.db import migrations


def _load_defaults_rows():
    import yaml

    fixtures_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'fixtures',
        'defaults.yaml',
    )
    with open(fixtures_path, 'r') as handle:
        return yaml.safe_load(handle) or []


def sync_tech_rebalance_from_defaults(apps, schema_editor):
    ResearchCategory = apps.get_model('dj4xol', 'ResearchCategory')
    Technology = apps.get_model('dj4xol', 'Technology')
    ResearchLevelPrerequisite = apps.get_model('dj4xol', 'ResearchLevelPrerequisite')

    category_fields = {field.name for field in ResearchCategory._meta.fields}
    prerequisite_fields = {
        field.name for field in ResearchLevelPrerequisite._meta.fields
    }

    rows = _load_defaults_rows()

    for row in rows:
        if row.get('model') != 'dj4xol.ResearchCategory':
            continue
        fields = dict(row.get('fields') or {})
        fields = {
            key: value
            for key, value in fields.items()
            if key in category_fields
        }
        pk = row.get('pk')
        if pk is None:
            continue
        ResearchCategory.objects.update_or_create(id=int(pk), defaults=fields)

    for row in rows:
        if row.get('model') != 'dj4xol.Technology':
            continue
        fields = dict(row.get('fields') or {})
        pk = row.get('pk')
        if not pk:
            continue
        if 'category' in fields and 'category_id' not in fields:
            fields['category_id'] = fields.pop('category')
        tech_id = uuid.UUID(str(pk))
        technology = Technology.objects.filter(id=tech_id).first()
        if technology is None:
            short_id = fields.get('short_id')
            if short_id:
                technology = Technology.objects.filter(short_id=short_id).first()
        if technology is None:
            Technology.objects.create(id=tech_id, **fields)
            continue
        for key, value in fields.items():
            setattr(technology, key, value)
        technology.save()

    for row in rows:
        if row.get('model') != 'dj4xol.ResearchLevelPrerequisite':
            continue
        fields = dict(row.get('fields') or {})
        fields = {
            key: value
            for key, value in fields.items()
            if key in prerequisite_fields
        }
        if 'category' in fields and 'category_id' not in fields:
            fields['category_id'] = fields.pop('category')
        if 'requires_category' in fields and 'requires_category_id' not in fields:
            fields['requires_category_id'] = fields.pop('requires_category')
        category_id = fields.pop('category_id', None)
        level = fields.pop('level', None)
        requires_category_id = fields.pop('requires_category_id', None)
        if category_id is None or level is None or requires_category_id is None:
            continue
        ResearchLevelPrerequisite.objects.update_or_create(
            category_id=category_id,
            level=level,
            requires_category_id=requires_category_id,
            defaults=fields,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0125_auto_20260306_1640'),
    ]

    operations = [
        migrations.RunPython(
            sync_tech_rebalance_from_defaults,
            migrations.RunPython.noop,
        ),
    ]
