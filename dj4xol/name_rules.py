import re

from django.core.exceptions import ValidationError


RESERVED_IDENTITY_NAMES = {
    'abandoned',
}

BLOCKED_PROFANITY = {
    'arse',
    'asshole',
    'bastard',
    'bitch',
    'bollocks',
    'bullshit',
    'cock',
    'crap',
    'cunt',
    'damn',
    'dick',
    'fag',
    'fuck',
    'fucker',
    'fucking',
    'motherfucker',
    'nigger',
    'piss',
    'prick',
    'shit',
    'slut',
    'twat',
    'wanker',
    'whore',
}

SAFE_TEXT_RE = re.compile(r"^[A-Za-z0-9 _.,!?\-()'+=&:/*\n\r]*\Z")
SAFE_SINGLE_LINE_RE = re.compile(r"^[A-Za-z0-9 _.,!?\-()'+=&:/*]*\Z")
SAFE_TEXT_TRANSLATION = str.maketrans({
    '\u2018': "'",
    '\u2019': "'",
    '\u201b': "'",
    '\u2032': "'",
    '\uff07': "'",
    '\u2010': '-',
    '\u2011': '-',
    '\u2012': '-',
    '\u2013': '-',
    '\u2014': '-',
    '\u2212': '-',
    '\ufe58': '-',
    '\ufe63': '-',
    '\uff0d': '-',
    '\uff08': '(',
    '\uff09': ')',
    '\uff06': '&',
    '\ufe60': '&',
    '\uff01': '!',
    '\uff1f': '?',
})


def normalise_public_text(value):
    if value is None:
        return ''
    return str(value).translate(SAFE_TEXT_TRANSLATION).strip()


def normalise_profanity_key(value):
    text = normalise_public_text(value).lower()
    return ''.join(ch for ch in text if ch.isalnum())


def parse_profanity_terms(raw_value):
    text = normalise_public_text(raw_value)
    if not text:
        return set()
    parts = re.split(r'[\s,]+', text)
    return {normalise_profanity_key(part) for part in parts if normalise_profanity_key(part)}


def contains_blocked_profanity(value, whitelist=None, blacklist=None):
    text = normalise_public_text(value).lower()
    if not text:
        return False
    whitelist = {term for term in (whitelist or set()) if term}
    blacklist = {term for term in (blacklist or set()) if term}
    tokens = re.findall(r"[a-z0-9']+", text)
    condensed = [''.join(ch for ch in token if ch.isalnum()) for token in tokens]
    collapsed = normalise_profanity_key(text)
    collapsed_for_check = collapsed
    for allowed in whitelist:
        if allowed:
            collapsed_for_check = collapsed_for_check.replace(allowed, '')
    blocked_terms = set(BLOCKED_PROFANITY).union(blacklist)
    for token in condensed:
        if not token:
            continue
        if any(
            token == blocked or token.startswith(blocked) or token.endswith(blocked)
            for blocked in blocked_terms
            if blocked not in whitelist
        ):
            return True
    if collapsed_for_check:
        for blocked in blocked_terms:
            if blocked in whitelist:
                continue
            if blocked and blocked in collapsed_for_check:
                return True
    return False


def validate_safe_public_text(
    value,
    label='Text',
    allow_newlines=False,
    block_profanity=True,
    profanity_whitelist=None,
    profanity_blacklist=None,
):
    text = normalise_public_text(value)
    if not text:
        return text
    pattern = SAFE_TEXT_RE if allow_newlines else SAFE_SINGLE_LINE_RE
    if not pattern.match(text):
        raise ValidationError(
            '%s contains unsupported characters. Use plain ASCII letters, numbers, spaces, and simple punctuation only.' % label
        )
    if block_profanity and contains_blocked_profanity(
        text,
        whitelist=profanity_whitelist,
        blacklist=profanity_blacklist,
    ):
        raise ValidationError('%s contains blocked profanity.' % label)
    return text


def validate_public_name(
    value,
    label='Name',
    block_profanity=True,
    profanity_whitelist=None,
    profanity_blacklist=None,
):
    text = validate_safe_public_text(
        value,
        label=label,
        allow_newlines=False,
        block_profanity=block_profanity,
        profanity_whitelist=profanity_whitelist,
        profanity_blacklist=profanity_blacklist,
    )
    if is_reserved_identity_name(text):
        raise ValidationError('%s is reserved.' % label)
    return text


def is_reserved_identity_name(value):
    """Return True when the supplied player/account/race name is reserved."""
    if value is None:
        return False
    return str(value).strip().lower() in RESERVED_IDENTITY_NAMES


def validate_non_reserved_identity_name(
    value,
    label='Name',
    block_profanity=True,
    profanity_whitelist=None,
    profanity_blacklist=None,
):
    """Reject reserved, profane, or unsafe public-facing names."""
    return validate_public_name(
        value,
        label=label,
        block_profanity=block_profanity,
        profanity_whitelist=profanity_whitelist,
        profanity_blacklist=profanity_blacklist,
    )
