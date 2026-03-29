# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json

from django.db import migrations


COMPARISON_OPERATORS = ('=', '==', '!=', '>', '<', '>=', '<=')


def _safe_params(params_json):
    try:
        data = json.loads(params_json or '{}')
        if isinstance(data, dict):
            return data
    except (TypeError, ValueError):
        pass
    return {}


def _tokenise(expression):
    text = str(expression or '').strip()
    if not text:
        return []
    return [token for token in text.split() if token]


def _is_safe_identifier(token):
    text = str(token or '').strip()
    if not text or text.startswith('_'):
        return False
    for char in text:
        if not (char.isalnum() or char == '_'):
            return False
    return True


def _parse_scalar(token):
    text = str(token or '').strip()
    lower = text.lower()
    if lower in ('true', 'yes', 'on'):
        return True
    if lower in ('false', 'no', 'off'):
        return False
    try:
        if '.' in text:
            return float(text)
        return int(text)
    except (TypeError, ValueError):
        return text


def _parse_race_type_requirement(expression):
    tokens = _tokenise(expression)
    if not tokens:
        return None

    lower_tokens = [token.lower() for token in tokens]
    if lower_tokens[0] == 'has':
        if len(tokens) == 2 and _is_safe_identifier(tokens[1]):
            return {
                'kind': 'has',
                'field': tokens[1],
            }
        if (
            len(tokens) == 4 and
            _is_safe_identifier(tokens[1]) and
            tokens[2] in COMPARISON_OPERATORS
        ):
            return {
                'kind': 'compare',
                'field': tokens[1],
                'operator': tokens[2],
                'value': _parse_scalar(tokens[3]),
            }
        return None

    if len(tokens) == 1 and _is_safe_identifier(tokens[0]):
        return {
            'kind': 'code',
            'code': tokens[0],
            'negate': False,
        }

    idx = 0
    if lower_tokens[0] == 'is':
        idx += 1
    negate = False
    if idx < len(tokens) and lower_tokens[idx] == 'not':
        negate = True
        idx += 1
    if idx == len(tokens) - 1 and _is_safe_identifier(tokens[idx]):
        return {
            'kind': 'code',
            'code': tokens[idx],
            'negate': negate,
        }
    return None


def _split_requirement_clauses(expression):
    if isinstance(expression, (list, tuple)):
        clauses = []
        for item in expression:
            clauses.append({'operator': 'or', 'expression': item})
        return clauses

    text = str(expression or '').strip()
    if not text or ',' not in text:
        return None

    parts = [part.strip() for part in text.split(',') if str(part or '').strip()]
    if len(parts) <= 1:
        return None

    clauses = []
    for part in parts:
        operator = 'or'
        clause = part
        lower = part.lower()
        if lower.startswith('and '):
            operator = 'and'
            clause = part[4:].strip()
        elif lower.startswith('or '):
            operator = 'or'
            clause = part[3:].strip()
        if clause:
            clauses.append({'operator': operator, 'expression': clause})
    return clauses or None


def _race_type_requirement_matches(expression, race_type):
    clauses = _split_requirement_clauses(expression)
    if clauses:
        matched = None
        for idx, clause in enumerate(clauses):
            clause_match = _race_type_requirement_matches(
                clause['expression'],
                race_type,
            )
            if idx == 0 or matched is None:
                matched = clause_match
                continue
            if clause['operator'] == 'and':
                matched = bool(matched) and bool(clause_match)
            else:
                matched = bool(matched) or bool(clause_match)
        return bool(matched)

    parsed = _parse_race_type_requirement(expression)
    if parsed is None or race_type is None:
        return False

    if parsed['kind'] == 'code':
        current = str(getattr(race_type, 'code', '') or '').upper()
        expected = str(parsed['code'] or '').upper()
        matched = current == expected
        if parsed.get('negate'):
            return not matched
        return matched

    field = parsed['field']
    if not _is_safe_identifier(field) or not hasattr(race_type, field):
        return False
    current = getattr(race_type, field)

    if parsed['kind'] == 'has':
        return bool(current)

    operator = parsed['operator']
    expected = parsed['value']

    if isinstance(current, bool) or isinstance(expected, bool):
        if operator in ('=', '=='):
            return bool(current) == bool(expected)
        if operator == '!=':
            return bool(current) != bool(expected)
        return False

    try:
        current_num = float(current)
        expected_num = float(expected)
        if operator in ('=', '=='):
            return current_num == expected_num
        if operator == '!=':
            return current_num != expected_num
        if operator == '>':
            return current_num > expected_num
        if operator == '<':
            return current_num < expected_num
        if operator == '>=':
            return current_num >= expected_num
        if operator == '<=':
            return current_num <= expected_num
    except (TypeError, ValueError):
        current_text = str(current or '').strip().lower()
        expected_text = str(expected or '').strip().lower()
        if operator in ('=', '=='):
            return current_text == expected_text
        if operator == '!=':
            return current_text != expected_text
    return False


def _technology_is_available_for_race_type(technology, race_type):
    params = _safe_params(getattr(technology, 'params_json', '{}'))
    expression = params.get('race_type')
    if expression in (None, ''):
        return True
    return _race_type_requirement_matches(expression, race_type)


def backfill_research_technology_grants(apps, schema_editor):
    Game = apps.get_model('dj4xol', 'Game')
    Player = apps.get_model('dj4xol', 'Player')
    Technology = apps.get_model('dj4xol', 'Technology')
    PlayerResearch = apps.get_model('dj4xol', 'PlayerResearch')
    PlayerTechnologyGrant = apps.get_model('dj4xol', 'PlayerTechnologyGrant')

    game_year_by_id = {
        game_id: int(year or 0)
        for game_id, year in Game.objects.values_list('id', 'year')
    }

    techs_by_category = {}
    for tech in Technology.objects.filter(enabled=True).order_by(
        'category_id', 'level', 'display_order', 'name', 'id'
    ).iterator():
        techs_by_category.setdefault(int(tech.category_id), []).append(tech)

    for player in Player.objects.select_related('race_type').iterator():
        level_by_category = {}
        for category_id, current_level in PlayerResearch.objects.filter(
            player_id=player.id
        ).values_list('category_id', 'current_level'):
            try:
                level_by_category[int(category_id)] = int(current_level or 0)
            except (TypeError, ValueError):
                level_by_category[int(category_id)] = 0
        if not level_by_category:
            continue

        existing_tech_ids = set(
            PlayerTechnologyGrant.objects.filter(player_id=player.id)
            .values_list('technology_id', flat=True)
        )
        grants_to_create = []
        granted_year = int(game_year_by_id.get(player.game_id, 0) or 0)
        race_type = getattr(player, 'race_type', None)

        for category_id, current_level in level_by_category.items():
            for tech in techs_by_category.get(int(category_id), ()):
                tech_id = getattr(tech, 'id', None)
                if tech_id is None or tech_id in existing_tech_ids:
                    continue
                try:
                    tech_level = int(getattr(tech, 'level', 0) or 0)
                except (TypeError, ValueError):
                    tech_level = 0
                if tech_level > int(current_level):
                    continue
                if not _technology_is_available_for_race_type(tech, race_type):
                    continue
                grants_to_create.append(PlayerTechnologyGrant(
                    player_id=player.id,
                    technology_id=tech_id,
                    obtained_via_diplomacy=False,
                    granted_year=granted_year,
                ))
                existing_tech_ids.add(tech_id)

        if grants_to_create:
            PlayerTechnologyGrant.objects.bulk_create(grants_to_create)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0204_add_player_technology_source_flags'),
    ]

    operations = [
        migrations.RunPython(
            backfill_research_technology_grants,
            migrations.RunPython.noop,
        ),
    ]
