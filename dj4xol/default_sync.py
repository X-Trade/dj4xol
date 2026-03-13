"""Sync factory default race/research/technology rows from fixtures."""

import os
import uuid

from django.db import connection, transaction


_SYNC_DONE_PATHS = set()
_DEFAULTS_CACHE = {}


def _default_fixture_path():
    return os.path.join(os.path.dirname(__file__), 'fixtures', 'defaults.yaml')


def _normalize_fixture_path(fixture_path=None):
    return os.path.abspath(fixture_path or _default_fixture_path())


def _load_defaults(fixture_path=None):
    fixture_key = _normalize_fixture_path(fixture_path)
    if fixture_key in _DEFAULTS_CACHE:
        return _DEFAULTS_CACHE[fixture_key]
    import yaml

    with open(fixture_key, 'r') as handle:
        _DEFAULTS_CACHE[fixture_key] = yaml.safe_load(handle) or []
    return _DEFAULTS_CACHE[fixture_key]


def _entries_for(model_label, fixture_path=None):
    return [row for row in _load_defaults(fixture_path) if row.get('model') == model_label]


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


def _table_column_names(table_name):
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table_name)
    return [getattr(column, 'name', column[0]) for column in description]


def _legacy_server_race_type_defaults():
    return {
        'gravity_center': 1.0,
        'gravity_width': 1.0,
        'temperature_center': 1.0,
        'temperature_width': 1.0,
        'radiation_center': 1.0,
        'radiation_width': 1.0,
        'starting_population': 1000,
        'starting_planet_has_massdriver': False,
        'metalurgy_multiplier': 1.0,
        'persuasion_multiplier': 1.0,
        'chance_of_scantheft': 0.01,
        'requires_space_station': False,
        'starting_research_points': 3,
    }


def _upsert_server_race_type(ServerRaceType, pk, fields):
    table_name = ServerRaceType._meta.db_table
    table_columns = set(_table_column_names(table_name))
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT 1 FROM {table} WHERE {pk_column} = %s LIMIT 1'.format(
                table=connection.ops.quote_name(table_name),
                pk_column=connection.ops.quote_name('code'),
            ),
            [pk],
        )
        exists = cursor.fetchone() is not None

    persisted_fields = {}
    for field in ServerRaceType._meta.concrete_fields:
        if field.column not in table_columns:
            continue
        if field.primary_key:
            continue
        if field.name in fields:
            persisted_fields[field.column] = fields[field.name]
            continue
        default = field.get_default()
        persisted_fields[field.column] = default() if callable(default) else default

    for column, value in _legacy_server_race_type_defaults().items():
        if column in table_columns and column not in persisted_fields:
            persisted_fields[column] = value

    if 'starting_planets' in table_columns and 'starting_planets' not in persisted_fields:
        if 'starting_colonies' in fields:
            persisted_fields['starting_planets'] = fields['starting_colonies']
        else:
            persisted_fields['starting_planets'] = 1
    if (
        'starting_colonies' in table_columns and
        'starting_planets' in fields and
        'starting_colonies' not in persisted_fields
    ):
        persisted_fields['starting_colonies'] = fields['starting_planets']
    if 'warp_multiplier' in table_columns and 'warp_multiplier' not in persisted_fields:
        if 'warp_advantage' in fields:
            persisted_fields['warp_multiplier'] = float(fields['warp_advantage']) + 1.0
        else:
            persisted_fields['warp_multiplier'] = 1.0
    if 'warp_advantage' in table_columns and 'warp_advantage' not in persisted_fields:
        if 'warp_multiplier' in fields:
            persisted_fields['warp_advantage'] = float(fields['warp_multiplier']) - 1.0
        else:
            persisted_fields['warp_advantage'] = 0.0
    if 'has_stealth' in table_columns and 'has_stealth' not in persisted_fields:
        if 'has_no_stealth' in fields:
            persisted_fields['has_stealth'] = not bool(fields['has_no_stealth'])
        else:
            persisted_fields['has_stealth'] = False
    if 'has_no_stealth' in table_columns and 'has_no_stealth' not in persisted_fields:
        if 'has_stealth' in fields:
            persisted_fields['has_no_stealth'] = not bool(fields['has_stealth'])
        else:
            persisted_fields['has_no_stealth'] = False

    if exists:
        update_columns = [column for column in persisted_fields.keys() if column != 'code']
        if not update_columns:
            return
        sql = 'UPDATE {table} SET {assignments} WHERE {pk_column} = %s'.format(
            table=connection.ops.quote_name(table_name),
            assignments=', '.join(
                '{column} = %s'.format(column=connection.ops.quote_name(column))
                for column in update_columns
            ),
            pk_column=connection.ops.quote_name('code'),
        )
        with connection.cursor() as cursor:
            cursor.execute(
                sql,
                [persisted_fields[column] for column in update_columns] + [pk],
            )
        return

    insert_fields = {'code': pk}
    insert_fields.update(persisted_fields)
    columns = list(insert_fields.keys())
    sql = 'INSERT INTO {table} ({columns}) VALUES ({placeholders})'.format(
        table=connection.ops.quote_name(table_name),
        columns=', '.join(connection.ops.quote_name(column) for column in columns),
        placeholders=', '.join(['%s'] * len(columns)),
    )
    with connection.cursor() as cursor:
        cursor.execute(sql, [insert_fields[column] for column in columns])


@transaction.atomic
def sync_factory_defaults(force=False, fixture_path=None):
    """Upsert fixture-backed defaults and update drifted values.

    Technologies are matched by UUID `pk`.
    Research categories are matched by fixture `pk` (integer id).
    Race types are matched by fixture `pk` (code).
    """
    fixture_key = _normalize_fixture_path(fixture_path)
    if fixture_key in _SYNC_DONE_PATHS and not force:
        return

    from .models import (
        ResearchCategory,
        ResearchLevelPrerequisite,
        ServerRace,
        ServerRaceType,
        Technology,
    )

    for row in _entries_for('dj4xol.ServerRaceType', fixture_path=fixture_key):
        fields = dict(row.get('fields') or {})
        pk = row.get('pk') or fields.get('code')
        if not pk:
            continue
        fields = _normalize_fk_fields(ServerRaceType, fields)
        _upsert_server_race_type(ServerRaceType, pk, fields)

    for row in _entries_for('dj4xol.ResearchCategory', fixture_path=fixture_key):
        pk = row.get('pk')
        fields = dict(row.get('fields') or {})
        if pk is None:
            continue
        fields = _normalize_fk_fields(ResearchCategory, fields)
        ResearchCategory.objects.update_or_create(id=pk, defaults=fields)

    for row in _entries_for('dj4xol.ServerRace', fixture_path=fixture_key):
        pk = row.get('pk')
        fields = dict(row.get('fields') or {})
        if not pk:
            continue
        fields = _normalize_fk_fields(ServerRace, fields)
        ServerRace.objects.update_or_create(id=pk, defaults=fields)

    for row in _entries_for('dj4xol.Technology', fixture_path=fixture_key):
        pk = row.get('pk')
        fields = dict(row.get('fields') or {})
        if not pk:
            continue
        fields = _normalize_fk_fields(Technology, fields)
        _upsert_technology(Technology, pk, fields)

    for row in _entries_for('dj4xol.ResearchLevelPrerequisite', fixture_path=fixture_key):
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

    _SYNC_DONE_PATHS.add(fixture_key)
