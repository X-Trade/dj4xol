"""Sync factory default race/research/technology rows from fixtures."""

import os
import uuid

from django.db import transaction


_SYNC_DONE = False
_DEFAULTS_CACHE = None


def _load_defaults():
    global _DEFAULTS_CACHE
    if _DEFAULTS_CACHE is not None:
        return _DEFAULTS_CACHE
    import yaml

    fixtures_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'defaults.yaml')
    with open(fixtures_path, 'r') as handle:
        _DEFAULTS_CACHE = yaml.safe_load(handle) or []
    return _DEFAULTS_CACHE


def _entries_for(model_label):
    return [row for row in _load_defaults() if row.get('model') == model_label]


def _normalize_fk_fields(model, fields):
    """Convert fixture FK keys to Django's `<field>_id` assignment form."""
    normalized = dict(fields)
    for field in model._meta.fields:
        rel = getattr(field, 'remote_field', None)
        if rel is None:
            continue
        name = field.name
        id_name = field.attname
        if name in normalized and id_name not in normalized:
            normalized[id_name] = normalized.pop(name)
    return normalized


def _upsert_technology(Technology, pk, fields):
    """Update fixture-backed technology rows, reconciling by short_id if needed."""
    tech_id = uuid.UUID(str(pk))
    technology = Technology.objects.filter(id=tech_id).first()
    if technology is None:
        short_id = fields.get('short_id')
        if short_id:
            technology = Technology.objects.filter(short_id=short_id).first()
    if technology is None:
        Technology.objects.create(id=tech_id, **fields)
        return
    for key, value in fields.items():
        setattr(technology, key, value)
    technology.save()


@transaction.atomic
def sync_factory_defaults(force=False):
    """Upsert fixture-backed defaults and update drifted values.

    Technologies are matched by UUID `pk`.
    Research categories are matched by fixture `pk` (integer id).
    Race types are matched by fixture `pk` (code).
    """
    global _SYNC_DONE
    if _SYNC_DONE and not force:
        return

    from .models import (
        ResearchCategory,
        ResearchLevelPrerequisite,
        ServerRace,
        ServerRaceType,
        Technology,
    )

    for row in _entries_for('dj4xol.ServerRaceType'):
        fields = dict(row.get('fields') or {})
        pk = row.get('pk') or fields.get('code')
        if not pk:
            continue
        fields = _normalize_fk_fields(ServerRaceType, fields)
        ServerRaceType.objects.update_or_create(code=pk, defaults=fields)

    for row in _entries_for('dj4xol.ResearchCategory'):
        pk = row.get('pk')
        fields = dict(row.get('fields') or {})
        if pk is None:
            continue
        fields = _normalize_fk_fields(ResearchCategory, fields)
        ResearchCategory.objects.update_or_create(id=pk, defaults=fields)

    for row in _entries_for('dj4xol.ServerRace'):
        pk = row.get('pk')
        fields = dict(row.get('fields') or {})
        if not pk:
            continue
        fields = _normalize_fk_fields(ServerRace, fields)
        ServerRace.objects.update_or_create(id=pk, defaults=fields)

    for row in _entries_for('dj4xol.Technology'):
        pk = row.get('pk')
        fields = dict(row.get('fields') or {})
        if not pk:
            continue
        fields = _normalize_fk_fields(Technology, fields)
        _upsert_technology(Technology, pk, fields)

    for row in _entries_for('dj4xol.ResearchLevelPrerequisite'):
        fields = dict(row.get('fields') or {})
        fields = _normalize_fk_fields(ResearchLevelPrerequisite, fields)
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

    _SYNC_DONE = True
