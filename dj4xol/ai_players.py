from __future__ import unicode_literals

from .models import server_setting_enabled, server_setting_int


AI_MODULE_MICROMANAGER = 'micromanager'
AI_MODULE_IDLE = 'idle'

AI_MODULE_ORDER = (
    AI_MODULE_MICROMANAGER,
    AI_MODULE_IDLE,
)

AI_MODULE_SPECS = {
    AI_MODULE_MICROMANAGER: {
        'label': 'Micromanager',
        'description': 'Uses max-tier Administration behavior across all colonies, including tier-5 fleet automation.',
        'administration_tier': 5,
        'default_enabled': True,
    },
    AI_MODULE_IDLE: {
        'label': 'Idle',
        'description': 'Uses tier-3 Administration behavior across all colonies.',
        'administration_tier': 3,
        'default_enabled': True,
    },
}


def normalize_ai_module_code(code):
    return str(code or '').strip().lower()


def get_ai_module_spec(code):
    return AI_MODULE_SPECS.get(normalize_ai_module_code(code))


def _enabled_setting_key(code):
    return 'ai_module_%s_enabled' % normalize_ai_module_code(code)


def is_ai_module_enabled(code):
    spec = get_ai_module_spec(code)
    if not spec:
        return False
    return server_setting_enabled(
        _enabled_setting_key(code),
        default=bool(spec.get('default_enabled', False)),
    )


def get_enabled_ai_modules():
    modules = []
    for code in AI_MODULE_ORDER:
        spec = get_ai_module_spec(code)
        if not spec:
            continue
        if not is_ai_module_enabled(code):
            continue
        entry = {'code': code}
        entry.update(spec)
        modules.append(entry)
    return modules


def ai_module_choices(enabled_only=False):
    if enabled_only:
        return [
            (entry['code'], entry.get('label', entry['code'].title()))
            for entry in get_enabled_ai_modules()
        ]
    pairs = []
    for code in AI_MODULE_ORDER:
        spec = get_ai_module_spec(code)
        if not spec:
            continue
        pairs.append((code, spec.get('label', code.title())))
    return pairs


def ai_module_administration_tier(code):
    spec = get_ai_module_spec(code)
    if not spec:
        return 0
    try:
        return max(0, int(spec.get('administration_tier', 0) or 0))
    except (TypeError, ValueError):
        return 0


def player_ai_administration_tier(player):
    if not player or not bool(getattr(player, 'is_ai', False)):
        return 0
    module_code = normalize_ai_module_code(getattr(player, 'ai_module', ''))
    if not module_code:
        return 0
    if not is_ai_module_enabled(module_code):
        return 0
    return ai_module_administration_tier(module_code)


def get_ai_max_per_game():
    return max(0, int(server_setting_int('ai_max_per_game', 0) or 0))


def get_ai_max_per_server():
    return max(0, int(server_setting_int('ai_max_per_server', 0) or 0))


def get_ai_check_in_turns():
    return max(1, int(server_setting_int('ai_check_in_turns', 1) or 1))


def count_active_ai_players():
    from .models import Player

    return Player.objects.filter(
        is_ai=True,
        defeated=False,
        game__ended=False,
    ).count()


def get_remaining_server_ai_capacity():
    max_server = get_ai_max_per_server()
    if max_server <= 0:
        return 0
    return max(0, max_server - count_active_ai_players())


def get_create_game_ai_capacity():
    max_game = get_ai_max_per_game()
    if max_game <= 0:
        return 0
    return min(max_game, get_remaining_server_ai_capacity())
