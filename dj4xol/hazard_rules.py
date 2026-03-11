import hashlib
from math import pow

from .models import Anomaly, Salvage


DANGER_NONE = 'NONE'
DANGER_LOW = 'LOW'
DANGER_MEDIUM = 'MEDIUM'
DANGER_HIGH = 'HIGH'

DANGER_LEVEL_LABELS = {
    DANGER_NONE: 'None',
    DANGER_LOW: 'Low',
    DANGER_MEDIUM: 'Medium',
    DANGER_HIGH: 'High',
}

_BASE_DANGER_FACTOR = {
    DANGER_NONE: 0.0,
    DANGER_LOW: 0.34,
    DANGER_MEDIUM: 0.67,
    DANGER_HIGH: 1.0,
}

_DAMAGE_CURVE = {
    DANGER_NONE: (0.0, 0.0),
    DANGER_LOW: (0.10, 0.45),
    DANGER_MEDIUM: (0.45, 0.70),
    DANGER_HIGH: (0.75, 0.85),
}

_REWARD_CURVE = {
    DANGER_NONE: (0.0, 0.0),
    DANGER_LOW: (0.20, 0.60),
    DANGER_MEDIUM: (0.50, 0.80),
    DANGER_HIGH: (0.75, 0.85),
}

_TRIGGER_CHANCE = {
    DANGER_NONE: 0.0,
    DANGER_LOW: 0.45,
    DANGER_MEDIUM: 0.70,
    DANGER_HIGH: 1.0,
}


def _stable_seed_value(seed):
    text = str(seed or '').encode('utf-8')
    return int(hashlib.md5(text).hexdigest()[:8], 16)


def _pick_level(seed, options):
    if not options:
        return DANGER_NONE
    return options[_stable_seed_value(seed) % len(options)]


def danger_level_display(level):
    return DANGER_LEVEL_LABELS.get(str(level or '').upper(), 'Unknown')


def stability_danger_scale(stability):
    try:
        pct = float(stability)
    except (TypeError, ValueError):
        pct = 50.0
    pct = max(0.0, min(100.0, pct))
    exponent = 1.0 - ((pct / 100.0) * 2.0)
    return float(pow(2.0, exponent))


def anomaly_danger_level(anomaly):
    anomaly_type = str(getattr(anomaly, 'anomaly_type', '') or '').upper()
    seed = 'anomaly:%s:%s' % (
        getattr(anomaly, 'short_id', None) or getattr(anomaly, 'id', None) or '',
        getattr(anomaly, 'name', '') or '',
    )
    if anomaly_type == Anomaly.TYPE_COMET:
        return DANGER_LOW
    if anomaly_type == Anomaly.TYPE_NEBULA:
        return _pick_level(seed, [DANGER_LOW, DANGER_MEDIUM])
    if anomaly_type == Anomaly.TYPE_RIFT:
        return _pick_level(seed, [DANGER_LOW, DANGER_MEDIUM, DANGER_HIGH])
    if anomaly_type == Anomaly.TYPE_BLACK_HOLE:
        return _pick_level(seed, [DANGER_MEDIUM, DANGER_HIGH])
    if anomaly_type == Anomaly.TYPE_WORMHOLE:
        return DANGER_MEDIUM
    return DANGER_MEDIUM


def salvage_danger_level(salvage):
    stored_level = str(getattr(salvage, 'danger_level', '') or '').upper()
    if stored_level in DANGER_LEVEL_LABELS:
        return stored_level
    salvage_type = str(getattr(salvage, 'salvage_type', '') or '').upper()
    seed = 'salvage:%s:%s' % (
        getattr(salvage, 'short_id', None) or getattr(salvage, 'id', None) or '',
        getattr(salvage, 'name', '') or '',
    )
    if salvage_type == Salvage.TYPE_ANCIENT_DEBRIS:
        return _pick_level(seed, [DANGER_MEDIUM, DANGER_HIGH])
    if salvage_type == Salvage.TYPE_ASTEROID_FIELD:
        return _pick_level(seed, [DANGER_LOW, DANGER_MEDIUM])
    return _pick_level(seed, [DANGER_NONE, DANGER_LOW])


def object_danger_level(obj):
    if isinstance(obj, Anomaly):
        return anomaly_danger_level(obj)
    if isinstance(obj, Salvage):
        return salvage_danger_level(obj)
    return DANGER_NONE


def danger_intensity(level, stability=None):
    base = _BASE_DANGER_FACTOR.get(str(level or '').upper(), 0.0)
    scale = 1.0 if stability is None else stability_danger_scale(stability)
    return max(0.0, min(1.0, float(base) * float(scale)))


def damage_intensity_multiplier(level, stability=None):
    intensity = danger_intensity(level, stability)
    intercept, slope = _DAMAGE_CURVE.get(str(level or '').upper(), (0.0, 0.0))
    return float(intercept) + (float(slope) * float(intensity))


def reward_intensity_multiplier(level, stability=None):
    intensity = danger_intensity(level, stability)
    intercept, slope = _REWARD_CURVE.get(str(level or '').upper(), (0.0, 0.0))
    return float(intercept) + (float(slope) * float(intensity))


def hazard_trigger_chance(level):
    return _TRIGGER_CHANCE.get(str(level or '').upper(), 0.0)


def direct_destruction_allowed(level):
    return str(level or '').upper() not in (DANGER_NONE, DANGER_LOW)
