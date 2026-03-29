"""Rules for race-type-gated technologies."""


COMPARISON_OPERATORS = ('=', '==', '!=', '>', '<', '>=', '<=')
FIELD_LABEL_OVERRIDES = {
    'has_advanced_remoteminers': 'advanced remote miners',
    'has_advanced_stargates': 'advanced stargates',
    'has_generalised_research': 'generalised research',
    'has_no_stealth': 'no stealth systems',
    'has_superweapon': 'superweapon',
    'starting_planet_has_stargate': 'starting planet has stargate',
}


def _split_requirement_clauses(expression):
    """Return top-level requirement clauses with connectors.

    Supported forms:
    - list/tuple: implicit OR across items
    - comma-separated text: implicit OR, with optional "and"/"or" prefixes
      on subsequent clauses (e.g. ``"is SCI, and has has_no_stealth == False"``)
    """
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


def parse_race_type_requirement(expression):
    """Parse a minimal race-type requirement expression."""
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
                'raw_value': tokens[3],
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


def _humanise_field_name(field):
    text = str(field or '').strip()
    override = FIELD_LABEL_OVERRIDES.get(text)
    if override:
        return override[:1].upper() + override[1:]
    if text.startswith('has_'):
        text = text[4:]
    text = text.replace('_', ' ')
    if not text:
        return ''
    return text[0].upper() + text[1:]


def describe_race_type_requirement(expression):
    """Return a human-readable description of a requirement expression."""
    clauses = _split_requirement_clauses(expression)
    if clauses:
        parsed_clauses = []
        all_positive_codes = True
        for clause in clauses:
            parsed = parse_race_type_requirement(clause['expression'])
            parsed_clauses.append(parsed)
            if not parsed or parsed.get('kind') != 'code' or parsed.get('negate'):
                all_positive_codes = False

        if all_positive_codes and parsed_clauses:
            text = 'Is %s' % parsed_clauses[0]['code']
            for idx in range(1, len(parsed_clauses)):
                operator = clauses[idx]['operator']
                joiner = 'and' if operator == 'and' else 'or'
                text += ' %s %s' % (joiner, parsed_clauses[idx]['code'])
            return text

        described = []
        for idx, clause in enumerate(clauses):
            text = describe_race_type_requirement(clause['expression'])
            if not text:
                continue
            if idx == 0 or not described:
                described.append(text)
                continue
            joiner = ' and ' if clause['operator'] == 'and' else ' or '
            described.append(joiner + text)
        return ''.join(described)

    parsed = parse_race_type_requirement(expression)
    if parsed is None:
        return str(expression or '').strip()

    if parsed['kind'] == 'code':
        if parsed.get('negate'):
            return 'Is not %s' % parsed['code']
        return 'Is %s' % parsed['code']

    if parsed['kind'] == 'has':
        return 'Has %s' % _humanise_field_name(parsed['field']).lower()

    display_operator = parsed['operator']
    if display_operator in ('=', '=='):
        display_operator = 'is'
    elif display_operator == '!=':
        display_operator = 'is not'

    return 'Has %s %s %s' % (
        _humanise_field_name(parsed['field']).lower(),
        display_operator,
        parsed['raw_value'],
    )


def race_type_requirement_matches(expression, race_type):
    """Return True when the race type satisfies the expression."""
    clauses = _split_requirement_clauses(expression)
    if clauses:
        matched = None
        for idx, clause in enumerate(clauses):
            clause_match = race_type_requirement_matches(clause['expression'], race_type)
            if idx == 0 or matched is None:
                matched = clause_match
                continue
            if clause['operator'] == 'and':
                matched = bool(matched) and bool(clause_match)
            else:
                matched = bool(matched) or bool(clause_match)
        return bool(matched)

    parsed = parse_race_type_requirement(expression)
    if parsed is None:
        return False
    if race_type is None:
        return False

    if parsed['kind'] == 'code':
        current = str(getattr(race_type, 'code', '') or '').upper()
        expected = str(parsed['code'] or '').upper()
        matched = current == expected
        if parsed.get('negate'):
            return not matched
        return matched

    field = parsed['field']
    if not _is_safe_identifier(field):
        return False
    if not hasattr(race_type, field):
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


def race_type_requirement_viewer_status(expression, race_type):
    """Return viewer status for a gated technology row.

    Returns:
    - ``'included'`` when the selected race type specifically gets the technology
    - ``'excluded'`` when the selected race type is the one specifically blocked
    - ``None`` when the technology is not exceptional for the selected race type
    """
    clauses = _split_requirement_clauses(expression)
    if clauses:
        status = None
        for idx, clause in enumerate(clauses):
            clause_status = race_type_requirement_viewer_status(
                clause['expression'],
                race_type,
            )
            if idx == 0:
                status = clause_status
                continue
            if clause['operator'] == 'and':
                if status == 'excluded' or clause_status == 'excluded':
                    status = 'excluded'
                elif status == 'included' and clause_status == 'included':
                    status = 'included'
                else:
                    status = None
            else:
                if status == 'included' or clause_status == 'included':
                    status = 'included'
                elif status == 'excluded' or clause_status == 'excluded':
                    status = 'excluded'
                else:
                    status = None
        return status

    parsed = parse_race_type_requirement(expression)
    if parsed is None or race_type is None:
        return None

    if parsed['kind'] == 'code':
        current = str(getattr(race_type, 'code', '') or '').upper()
        expected = str(parsed['code'] or '').upper()
        if parsed.get('negate'):
            return 'excluded' if current == expected else None
        return 'included' if current == expected else None

    if parsed['kind'] == 'has':
        field = parsed['field']
        if not hasattr(race_type, field):
            return None
        return 'included' if bool(getattr(race_type, field, False)) else None

    field = parsed['field']
    if not hasattr(race_type, field):
        return None
    current = getattr(race_type, field)
    if isinstance(current, bool) or isinstance(parsed['value'], bool):
        current_bool = bool(current)
        expected_bool = bool(parsed['value'])
        if parsed['operator'] in ('=', '=='):
            if expected_bool:
                return 'included' if current_bool else None
            return 'excluded' if current_bool else None
        if parsed['operator'] == '!=':
            if expected_bool:
                return 'excluded' if current_bool else None
            return 'included' if current_bool else None
        return None
    if parsed['operator'] == '!=':
        expected = parsed['value']
        try:
            return 'excluded' if float(current) == float(expected) else None
        except (TypeError, ValueError):
            current_text = str(current or '').strip().lower()
            expected_text = str(expected or '').strip().lower()
            return 'excluded' if current_text == expected_text else None

    if race_type_requirement_matches(expression, race_type):
        return 'included'
    return None
