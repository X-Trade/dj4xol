"""Rules for race-type-gated technologies."""


COMPARISON_OPERATORS = ('=', '==', '!=', '>', '<', '>=', '<=')


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
    if text.startswith('has_'):
        text = text[4:]
    text = text.replace('_', ' ')
    if not text:
        return ''
    return text[0].upper() + text[1:]


def describe_race_type_requirement(expression):
    """Return a human-readable description of a requirement expression."""
    parsed = parse_race_type_requirement(expression)
    if parsed is None:
        return str(expression or '').strip()

    if parsed['kind'] == 'code':
        if parsed.get('negate'):
            return 'Is not %s' % parsed['code']
        return 'Is %s' % parsed['code']

    if parsed['kind'] == 'has':
        return 'Has %s' % _humanise_field_name(parsed['field']).lower()

    return 'Has %s %s %s' % (
        _humanise_field_name(parsed['field']).lower(),
        parsed['operator'],
        parsed['raw_value'],
    )


def race_type_requirement_matches(expression, race_type):
    """Return True when the race type satisfies the expression."""
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
