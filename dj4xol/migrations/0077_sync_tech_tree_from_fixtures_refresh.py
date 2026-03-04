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
        data = yaml.safe_load(handle) or []
    return data


def sync_tech_tree_from_fixtures_refresh(apps, schema_editor):
    ResearchCategory = apps.get_model('dj4xol', 'ResearchCategory')
    Technology = apps.get_model('dj4xol', 'Technology')
    category_fields = {field.name for field in ResearchCategory._meta.fields}

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

        Technology.objects.update_or_create(
            id=uuid.UUID(str(pk)),
            defaults=fields,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0076_auto_20260302_1700'),
    ]

    operations = [
        migrations.RunPython(
            sync_tech_tree_from_fixtures_refresh,
            migrations.RunPython.noop,
        ),
    ]
