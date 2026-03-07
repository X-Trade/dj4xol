from django.core.exceptions import ValidationError


RESERVED_IDENTITY_NAMES = {
    'abandoned',
}


def is_reserved_identity_name(value):
    """Return True when the supplied player/account/race name is reserved."""
    if value is None:
        return False
    return str(value).strip().lower() in RESERVED_IDENTITY_NAMES


def validate_non_reserved_identity_name(value, label='Name'):
    """Reject names reserved for neutral gameplay concepts."""
    if is_reserved_identity_name(value):
        raise ValidationError('%s is reserved.' % label)
    return value
