from __future__ import unicode_literals

import json
import logging
import math
import os
import random
import urllib.error
import urllib.request

from .models import ServerSettings, server_setting_enabled, server_setting_int


AI_MODULE_MICROMANAGER = 'micromanager'
AI_MODULE_EXPANSIONIST = 'expansionist'
AI_MODULE_IDLE = 'idle'
AI_MODULE_OPENAI = 'openai'
AI_SLOT_RANDOM_RACE = '__RANDOM__'
AI_SLOT_RANDOM_STANCE = 'RANDOM'
AI_RANDOM_STANCE_POOL = ('HOSTILE', 'COLD', 'NEUTRAL', 'WARM')

logger = logging.getLogger(__name__)

AI_MODULE_ORDER = (
    AI_MODULE_MICROMANAGER,
    AI_MODULE_EXPANSIONIST,
    AI_MODULE_IDLE,
    AI_MODULE_OPENAI,
)
AI_SERVER_CAP_EXCLUDED_MODULES = frozenset((
    AI_MODULE_MICROMANAGER,
    AI_MODULE_EXPANSIONIST,
    AI_MODULE_IDLE,
))
AI_MICROMANAGER_FAMILY_MODULES = frozenset((
    AI_MODULE_MICROMANAGER,
    AI_MODULE_EXPANSIONIST,
))

AI_MODULE_SPECS = {
    AI_MODULE_MICROMANAGER: {
        'label': 'Micromanager',
        'description': (
            'Uses tier-5 colony micromanager behavior across all colonies, '
            'regardless of built Administration structures or unlocked '
            'Administration tech, while still respecting research-gated '
            'production unlocks.'
        ),
        'administration_tier': 5,
        'default_enabled': True,
    },
    AI_MODULE_EXPANSIONIST: {
        'label': 'Expansionist',
        'description': (
            'Uses the Micromanager AI core with a stronger bias toward '
            'extraction, population growth, and colony expansion while still '
            'respecting research-gated production unlocks.'
        ),
        'administration_tier': 5,
        'default_enabled': True,
    },
    AI_MODULE_IDLE: {
        'label': 'Idle',
        'description': 'Uses tier-3 Administration behavior across all colonies.',
        'administration_tier': 3,
        'default_enabled': True,
    },
    AI_MODULE_OPENAI: {
        'label': 'OpenAI-Compatible',
        'description': (
            'Runs an OpenAI API-compatible command loop that drives the Play CLI '
            'for this AI player.'
        ),
        'administration_tier': 0,
        'default_enabled': False,
    },
}

_STANCE_ORDER = ('HOSTILE', 'COLD', 'NEUTRAL', 'WARM', 'ALLIED')


def normalize_ai_module_code(code):
    return str(code or '').strip().lower()


def get_ai_module_spec(code):
    return AI_MODULE_SPECS.get(normalize_ai_module_code(code))


def _enabled_setting_key(code):
    return 'ai_module_%s_enabled' % normalize_ai_module_code(code)


def _config_setting_key(code):
    return 'ai_module_%s_config' % normalize_ai_module_code(code)


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


def ai_module_counts_towards_server_cap(code):
    module_code = normalize_ai_module_code(code)
    if not module_code:
        # Unknown/legacy module values should be counted conservatively.
        return True
    return module_code not in AI_SERVER_CAP_EXCLUDED_MODULES


def ai_module_uses_micromanager_behavior(code):
    return normalize_ai_module_code(code) in AI_MICROMANAGER_FAMILY_MODULES


def micromanager_mode_for_module(code):
    module_code = normalize_ai_module_code(code)
    if module_code == AI_MODULE_EXPANSIONIST:
        return 'expansionist'
    return 'standard'


def micromanager_mode_for_player(player):
    if player is None:
        return 'standard'
    return micromanager_mode_for_module(getattr(player, 'ai_module', ''))


def get_ai_max_per_game():
    return max(0, int(server_setting_int('ai_max_per_game', 0) or 0))


def get_ai_max_per_server():
    return max(0, int(server_setting_int('ai_max_per_server', 0) or 0))


def get_ai_check_in_turns():
    return max(1, int(server_setting_int('ai_check_in_turns', 1) or 1))


def get_ai_module_config(code):
    raw = ServerSettings.get(_config_setting_key(code), '') or ''
    text = str(raw).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        logger.warning(
            'Invalid AI module config JSON for %s; using defaults.',
            normalize_ai_module_code(code),
        )
        return {}
    if isinstance(parsed, dict):
        return parsed
    logger.warning(
        'AI module config for %s is not a JSON object; using defaults.',
        normalize_ai_module_code(code),
    )
    return {}


def resolve_ai_slot_stance(raw_value):
    from .models import Player

    valid = {str(code or '').upper() for code, _label in Player.STANCE_CHOICES}
    stance = str(raw_value or '').strip().upper()
    if stance == AI_SLOT_RANDOM_STANCE:
        return random.choice(AI_RANDOM_STANCE_POOL)
    if stance in valid:
        return stance
    return 'NEUTRAL'


def _random_center_width_pair():
    width_steps = int(round((1.30 - 0.30) / 0.05))
    width = round(0.30 + (random.randint(0, width_steps) * 0.05), 2)
    half = width / 2.0
    min_center = half
    max_center = 2.0 - half
    center_steps = int(round((max_center - min_center) / 0.05))
    center = round(min_center + (random.randint(0, center_steps) * 0.05), 2)
    return center, width


def _apply_race_type_habitability_overrides(payload, race_type):
    mapping = (
        ('gravity', 'ignores_gravity'),
        ('temperature', 'ignores_temperature'),
        ('radiation', 'ignores_radiation'),
    )
    ignored_envs = set()
    for env, attr in mapping:
        if bool(getattr(race_type, attr, False)):
            payload['%s_center' % env] = 1.0
            payload['%s_width' % env] = 1.0
            ignored_envs.add(env)
    return ignored_envs


def _build_random_race_candidate(race_type, max_starting_tech_level):
    centers = {}
    widths = {}
    for env in ('gravity', 'temperature', 'radiation'):
        center, width = _random_center_width_pair()
        centers[env] = center
        widths[env] = width
    floor = 0
    ceiling = max(0, int(max_starting_tech_level or 0))
    if ceiling <= 2:
        tech_level = random.randint(floor, ceiling) if ceiling > floor else floor
    else:
        tech_level = random.randint(2, min(ceiling, 8))
    candidate = {
        'race_type': race_type,
        'gravity_center': centers['gravity'],
        'temperature_center': centers['temperature'],
        'radiation_center': centers['radiation'],
        'gravity_width': widths['gravity'],
        'temperature_width': widths['temperature'],
        'radiation_width': widths['radiation'],
        'starting_colonists': random.randint(20, 34),
        'starting_mines': random.randint(4, 10),
        'starting_factories': random.randint(2, 8),
        'starting_labs': random.randint(1, 4),
        'starting_shipyards': random.randint(1, 3),
        'starting_fleets': random.randint(2, 5),
        'starting_tech_level': tech_level,
        'convert_unused_buildpoints_to_research': False,
        'singular_research': False,
        'fixed_homeworld': False,
        'spend_leftover_points_on_research': False,
        'leftover_points': 0.0,
    }
    ignored = _apply_race_type_habitability_overrides(candidate, race_type)
    return candidate, ignored


def _build_race_rules(candidate):
    from .habitability_rules import RaceCreationRules
    from .research import get_starting_tech_balance_cost

    race_type = candidate['race_type']
    return RaceCreationRules(
        centers={
            'gravity': float(candidate['gravity_center']),
            'temperature': float(candidate['temperature_center']),
            'radiation': float(candidate['radiation_center']),
        },
        widths={
            'gravity': float(candidate['gravity_width']),
            'temperature': float(candidate['temperature_width']),
            'radiation': float(candidate['radiation_width']),
        },
        starting_colonists=int(candidate['starting_colonists']),
        starting_mines=int(candidate['starting_mines']),
        starting_factories=int(candidate['starting_factories']),
        starting_labs=int(candidate['starting_labs']),
        starting_shipyards=int(candidate['starting_shipyards']),
        starting_fleets=int(candidate['starting_fleets']),
        starting_tech_level=int(candidate['starting_tech_level']),
        starting_tech_level_cost=get_starting_tech_balance_cost(
            int(candidate['starting_tech_level'])
        ),
        race_type_points_balance=float(
            getattr(race_type, 'race_creation_points_balance', 0.0) or 0.0
        ),
        convert_unused_buildpoints_to_research=bool(
            candidate.get('convert_unused_buildpoints_to_research')
        ),
        singular_research=bool(candidate.get('singular_research')),
        fixed_homeworld=bool(candidate.get('fixed_homeworld')),
    )


def _reduce_candidate_to_budget(candidate, ignored_envs):
    budget = 120.0
    defaults = {
        'starting_colonists': 20,
        'starting_mines': 4,
        'starting_factories': 2,
        'starting_labs': 1,
        'starting_shipyards': 1,
        'starting_fleets': 2,
    }

    for _step in range(400):
        rules = _build_race_rules(candidate)
        if not rules.validate() and rules.total_cost() <= budget:
            return candidate, rules
        changed = False

        # First trim broad habitability widths down toward 0.6 where possible.
        for env in ('gravity', 'temperature', 'radiation'):
            if env in ignored_envs:
                continue
            width_key = '%s_width' % env
            width = float(candidate.get(width_key, 1.0) or 1.0)
            if width > 0.6:
                candidate[width_key] = round(max(0.6, width - 0.05), 2)
                changed = True
                break
        if changed:
            continue

        # Then pull expensive starting profile fields back to defaults.
        for field in (
            'starting_colonists',
            'starting_shipyards',
            'starting_fleets',
            'starting_factories',
            'starting_mines',
            'starting_labs',
        ):
            current = int(candidate.get(field, 0) or 0)
            floor = int(defaults.get(field, 0))
            if current > floor:
                candidate[field] = current - 1
                changed = True
                break
        if changed:
            continue

        # If still too expensive, continue narrowing non-overridden ranges.
        for env in ('gravity', 'temperature', 'radiation'):
            if env in ignored_envs:
                continue
            width_key = '%s_width' % env
            width = float(candidate.get(width_key, 1.0) or 1.0)
            if width > 0.1:
                candidate[width_key] = round(max(0.1, width - 0.05), 2)
                changed = True
                break
        if changed:
            continue

        if int(candidate.get('starting_tech_level', 0) or 0) > 0:
            candidate['starting_tech_level'] = int(candidate['starting_tech_level']) - 1
            changed = True
        if not changed:
            break

    return candidate, _build_race_rules(candidate)


def build_random_ai_race_template(max_starting_tech_level=None):
    """Return an unsaved ServerRace-like object with balanced randomized values."""
    from .models import ServerRace, ServerRaceType
    from .research import get_global_research_max_level

    max_level = (
        get_global_research_max_level()
        if max_starting_tech_level is None
        else max(0, int(max_starting_tech_level or 0))
    )
    race_types = list(ServerRaceType.objects.filter(enabled=True))
    if not race_types:
        race_types = list(ServerRaceType.objects.all())
    if not race_types:
        raise ValueError('No race types available for random AI race generation.')

    best_candidate = None
    best_rules = None
    for _attempt in range(64):
        race_type = random.choice(race_types)
        candidate, ignored_envs = _build_random_race_candidate(race_type, max_level)
        candidate, rules = _reduce_candidate_to_budget(candidate, ignored_envs)
        errors = rules.validate()
        if errors:
            continue
        total = float(rules.total_cost())
        if best_rules is None or total > float(best_rules.total_cost()):
            best_candidate = dict(candidate)
            best_rules = rules
        if total >= 112.0:
            break

    if best_candidate is None:
        race_type = random.choice(race_types)
        best_candidate = {
            'race_type': race_type,
            'gravity_center': 1.0,
            'gravity_width': 1.0,
            'temperature_center': 1.0,
            'temperature_width': 1.0,
            'radiation_center': 1.0,
            'radiation_width': 1.0,
            'starting_colonists': 20,
            'starting_mines': 4,
            'starting_factories': 2,
            'starting_labs': 1,
            'starting_shipyards': 1,
            'starting_fleets': 2,
            'starting_tech_level': max(0, min(max_level, 3)),
            'convert_unused_buildpoints_to_research': False,
            'singular_research': False,
            'fixed_homeworld': False,
            'spend_leftover_points_on_research': False,
            'leftover_points': 0.0,
        }
        _apply_race_type_habitability_overrides(best_candidate, race_type)

    token = '%04X' % random.randint(0, 0xFFFF)
    name = ('AI%s' % token)[:16]
    plural = ('%ss' % name)[:16]
    race = ServerRace(
        name=name,
        plural_name=plural,
        homeworld_name='',
        fixed_homeworld=bool(best_candidate.get('fixed_homeworld')),
        starting_colonists=int(best_candidate.get('starting_colonists', 20)),
        starting_mines=int(best_candidate.get('starting_mines', 4)),
        starting_factories=int(best_candidate.get('starting_factories', 2)),
        starting_labs=int(best_candidate.get('starting_labs', 1)),
        starting_shipyards=int(best_candidate.get('starting_shipyards', 1)),
        starting_fleets=int(best_candidate.get('starting_fleets', 2)),
        starting_tech_level=int(best_candidate.get('starting_tech_level', 3)),
        convert_unused_buildpoints_to_research=bool(
            best_candidate.get('convert_unused_buildpoints_to_research')
        ),
        singular_research=bool(best_candidate.get('singular_research')),
        spend_leftover_points_on_research=bool(
            best_candidate.get('spend_leftover_points_on_research')
        ),
        leftover_points=float(best_candidate.get('leftover_points', 0.0)),
        public=False,
        owner=None,
        description='',
        race_type=best_candidate['race_type'],
    )
    race.gravity_center = float(best_candidate['gravity_center'])
    race.gravity_width = float(best_candidate['gravity_width'])
    race.temperature_center = float(best_candidate['temperature_center'])
    race.temperature_width = float(best_candidate['temperature_width'])
    race.radiation_center = float(best_candidate['radiation_center'])
    race.radiation_width = float(best_candidate['radiation_width'])
    return race


def _bounded_int(value, default, minimum=None, maximum=None):
    try:
        out = int(value)
    except (TypeError, ValueError):
        out = int(default)
    if minimum is not None:
        out = max(int(minimum), out)
    if maximum is not None:
        out = min(int(maximum), out)
    return out


def _bounded_float(value, default, minimum=None, maximum=None):
    try:
        out = float(value)
    except (TypeError, ValueError):
        out = float(default)
    if minimum is not None:
        out = max(float(minimum), out)
    if maximum is not None:
        out = min(float(maximum), out)
    return out


def _truncate_text(text, limit):
    raw = str(text or '')
    cap = max(0, int(limit or 0))
    if cap <= 0 or len(raw) <= cap:
        return raw
    return raw[:cap] + '\n...(truncated)'


def _strip_markdown_fences(text):
    raw = str(text or '').strip()
    if not raw.startswith('```'):
        return raw
    lines = raw.splitlines()
    if len(lines) <= 1:
        return raw.strip('`').strip()
    if lines[-1].strip().startswith('```'):
        lines = lines[1:-1]
    else:
        lines = lines[1:]
    return '\n'.join(lines).strip()


def _extract_ai_decision(response_text):
    raw = _strip_markdown_fences(response_text)
    decision = {
        'command': '',
        'done': False,
        'note': '',
    }
    if not raw:
        return decision

    start = raw.find('{')
    end = raw.rfind('}')
    if start >= 0 and end > start:
        maybe_json = raw[start:end + 1]
        try:
            payload = json.loads(maybe_json)
        except Exception:
            payload = None
        if isinstance(payload, dict):
            command = str(payload.get('command') or '').strip()
            done = bool(payload.get('done', False))
            note = str(payload.get('note') or payload.get('reason') or '').strip()
            decision.update({
                'command': command,
                'done': done,
                'note': note,
            })
            return decision

    for line in raw.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if candidate.startswith('/'):
            decision['command'] = candidate
            return decision
        if candidate.lower() in ('done', 'stop', 'no-op', 'noop'):
            decision['done'] = True
            return decision
    decision['note'] = raw
    return decision


def _is_valid_ai_cli_command(command):
    raw = str(command or '').strip()
    if not raw or not raw.startswith('/'):
        return False
    cmd = raw.split()[0].lower()
    if cmd in ('/done', '/exit', '/quit', '/clear'):
        return False
    try:
        from .play_cli_web import _is_allowed_browser_command
    except Exception:
        return False
    return bool(_is_allowed_browser_command(raw))


class _AICLITranscriptCollector(object):
    def __init__(self):
        self.lines = []

    def write(self, msg="", style_func=None, ending="\n"):
        text = "" if msg is None else str(msg)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if text == "":
            self.lines.append("")
            return
        self.lines.extend(text.split("\n"))


def _execute_play_cli_command(game, player, command):
    from django.core.management.base import CommandError
    from dj4xol.management.commands.play import Command as PlayCommand

    collector = _AICLITranscriptCollector()
    runner = PlayCommand()
    runner.stdout = collector
    try:
        runner._execute_cli_command(str(command or '').strip(), player, game)
    except CommandError as exc:
        collector.write(str(exc))
    return '\n'.join(line for line in collector.lines if line is not None).strip()


def _build_openai_system_prompt(game, player, config):
    custom_instructions = str(config.get('system_prompt') or '').strip()
    base_prompt = (
        "You are controlling an AI player in DJ4XOL, a turn-based 4X space strategy game.\n"
        "Game short id: %s. Current year: %s.\n"
        "You are player '%s' (%s).\n\n"
        "Your role:\n"
        "- Use only Play CLI commands to inspect state and issue orders.\n"
        "- Improve economy, research, expansion, and survival.\n"
        "- Avoid invalid commands and avoid destructive no-op loops.\n"
        "- Return exactly one JSON object each iteration.\n\n"
        "Response format:\n"
        "{\"command\":\"/status\",\"done\":false,\"note\":\"optional short note\"}\n"
        "or\n"
        "{\"done\":true,\"note\":\"finished\"}\n\n"
        "Rules:\n"
        "- One command per response.\n"
        "- Do not include markdown code fences.\n"
        "- Do not use /done, /quit, /exit, or /clear.\n"
        "- Commands must be valid browser Play CLI commands.\n"
    ) % (game.short_id, game.year, player.name, player.short_id)
    if custom_instructions:
        base_prompt = base_prompt + "\nServer custom instructions:\n" + custom_instructions
    return base_prompt


def _trim_messages(messages, max_chars):
    budget = max(1024, int(max_chars or 0))
    while True:
        total = sum(len(str(item.get('content', ''))) for item in messages)
        if total <= budget:
            break
        if len(messages) <= 3:
            break
        # Keep system + initial state message; drop oldest rolling message.
        del messages[2]


def _openai_chat_completion(config, messages):
    model = str(config.get('model') or '').strip()
    if not model:
        raise ValueError('OpenAI module config is missing "model".')

    api_key = str(config.get('api_key') or '').strip() or str(
        os.environ.get('OPENAI_API_KEY', '') or ''
    ).strip()
    if not api_key:
        raise ValueError('OpenAI module config is missing "api_key".')

    api_base_url = str(config.get('api_base_url') or '').strip()
    if not api_base_url:
        api_base_url = 'https://api.openai.com/v1'
    api_base_url = api_base_url.rstrip('/')
    chat_url = str(config.get('chat_completions_url') or '').strip()
    if not chat_url:
        chat_url = '%s/chat/completions' % api_base_url

    payload = {
        'model': model,
        'messages': list(messages or []),
    }
    if 'temperature' in config:
        payload['temperature'] = _bounded_float(config.get('temperature'), 0.2, 0.0, 2.0)
    else:
        payload['temperature'] = 0.2
    if 'max_output_tokens' in config:
        payload['max_tokens'] = _bounded_int(config.get('max_output_tokens'), 250, 1, 4000)

    timeout_seconds = _bounded_float(config.get('timeout_seconds'), 25.0, 1.0, 120.0)

    request = urllib.request.Request(
        chat_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % api_key,
        },
    )
    try:
        response = urllib.request.urlopen(request, timeout=timeout_seconds)
        raw = response.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as exc:
        body = ''
        try:
            body = exc.read().decode('utf-8', 'replace')
        except Exception:
            body = str(exc)
        raise RuntimeError(
            'OpenAI-compatible API error (%s): %s'
            % (getattr(exc, 'code', 'unknown'), _truncate_text(body, 600))
        )
    except Exception as exc:
        raise RuntimeError('OpenAI-compatible API request failed: %s' % exc)

    try:
        data = json.loads(raw)
    except Exception:
        raise RuntimeError('OpenAI-compatible API returned non-JSON response.')
    choices = data.get('choices') or []
    if not choices:
        raise RuntimeError('OpenAI-compatible API response had no choices.')
    first = choices[0] or {}
    message = first.get('message') or {}
    content = message.get('content')
    if isinstance(content, list):
        bits = []
        for part in content:
            if isinstance(part, dict):
                if 'text' in part:
                    bits.append(str(part.get('text') or ''))
            else:
                bits.append(str(part))
        content = ''.join(bits)
    return str(content or '').strip()


def _build_openai_state_snapshot(game, player, config):
    default_commands = ['/status', '/colonies', '/fleets own', '/research', '/messages priority=1 limit=20']
    commands = config.get('snapshot_commands')
    if not isinstance(commands, list) or not commands:
        commands = default_commands
    limit = _bounded_int(config.get('snapshot_chars'), 12000, 1000, 50000)
    each_limit = _bounded_int(config.get('snapshot_command_chars'), 3000, 500, 10000)
    blocks = []
    total = 0
    for raw_cmd in commands:
        cmd = str(raw_cmd or '').strip()
        if not cmd:
            continue
        if not _is_valid_ai_cli_command(cmd):
            continue
        output = _execute_play_cli_command(game, player, cmd)
        block = '$ %s\n%s' % (cmd, _truncate_text(output, each_limit))
        if total + len(block) > limit:
            remaining = limit - total
            if remaining <= 0:
                break
            block = _truncate_text(block, remaining)
            blocks.append(block)
            break
        blocks.append(block)
        total += len(block)
    return '\n\n'.join(blocks).strip()


def _contract_bundle_value_kt(contract):
    if contract is None:
        return 0
    total = 0
    for key in ('ironium', 'boranium', 'germanium', 'resource_x', 'resource_y', 'resource_z', 'colonists'):
        total += max(0, int(getattr(contract, 'request_%s' % key, 0) or 0))
    return int(total)


def _fleet_build_value_kt():
    from .models import PRODUCTION_COSTS

    base = PRODUCTION_COSTS.get('BUILD_FLEET', {}) or {}
    total = 0
    for key in ('bp', 'ironium', 'boranium', 'germanium', 'resource_x', 'resource_y', 'resource_z', 'colonists'):
        total += max(0, int(base.get(key, 0) or 0))
    return int(total)


def _fleet_material_value_kt(fleet):
    if fleet is None:
        return 0
    ship_count = max(0, int(getattr(fleet, 'ship_count', 0) or 0))
    build_value = _fleet_build_value_kt() * ship_count
    cargo_value = 0
    for key in ('ironium', 'boranium', 'germanium', 'resource_x', 'resource_y', 'resource_z', 'colonists'):
        cargo_value += max(0, int(getattr(fleet, '%s_inventory' % key, 0) or 0))
    return int(build_value + cargo_value)


def _star_material_value_kt(star):
    if star is None:
        return 0
    total = 0
    for key in ('ironium', 'boranium', 'germanium', 'resource_x', 'resource_y', 'resource_z'):
        total += max(0, int(getattr(star, '%s_inventory' % key, 0) or 0))
        total += max(0, int(getattr(star, '%s_yield' % key, 0) or 0)) * 50
    return int(total)


def _technology_clause_value_kt(contract, prefix):
    technology = getattr(contract, '%s_technology' % prefix, None)
    if technology is None:
        return 0
    try:
        level = int(getattr(technology, 'level', 0) or 0)
    except (TypeError, ValueError):
        level = 0
    return int(250 + (max(0, level) * 125))


def _report_clause_value_kt(contract, prefix):
    from .models import Report

    if contract is None:
        return 0
    if prefix == 'request':
        source = getattr(contract, 'recipient', None)
    else:
        source = getattr(contract, 'sender', None)
    target_type = str(getattr(contract, '%s_report_target_type' % prefix, '') or '').strip()
    target_id = getattr(contract, '%s_report_target_id' % prefix, None)
    if source is None or not target_type or target_id is None:
        return 0
    report = Report.objects.filter(
        game=getattr(contract, 'game', None),
        player=source,
        target_type=target_type,
        target_id=target_id,
    ).first()
    if report is None:
        return 0
    data = report.get_report_data() or {}
    tier = str(data.get('report_tier') or '').strip().lower()
    tier_values = {
        'observed': 120,
        'basic': 250,
        'advanced': 520,
        'encounter': 700,
        'ownership': 900,
    }
    return int(tier_values.get(tier, 200))


def _stance_clause_value_kt(contract, prefix):
    if contract is None:
        return 0
    if prefix == 'request':
        source = getattr(contract, 'recipient', None)
        target = getattr(contract, 'sender', None)
    else:
        source = getattr(contract, 'sender', None)
        target = getattr(contract, 'recipient', None)
    requested = str(getattr(contract, '%s_stance' % prefix, '') or '').strip().upper()
    if source is None or target is None or not requested:
        return 0
    current = _current_stance_towards_sender(source, target)
    delta = _stance_rank(requested) - _stance_rank(current)
    if delta > 0:
        return int(180 + (delta * 320))
    if delta == 0:
        return 80
    return 40


def _contract_offer_value_kt(contract):
    from .models import DiplomaticContract

    if contract is None:
        return 0
    clause = str(getattr(contract, 'offer_clause_type', '') or '')
    if clause == DiplomaticContract.CLAUSE_TECHNOLOGY:
        return _technology_clause_value_kt(contract, 'offer')
    if clause == DiplomaticContract.CLAUSE_STANCE:
        return _stance_clause_value_kt(contract, 'offer')
    if clause == DiplomaticContract.CLAUSE_REPORT:
        return _report_clause_value_kt(contract, 'offer')
    if clause in (
        DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD,
        DiplomaticContract.CLAUSE_RESOURCE_ON_GIVEN_FLEET,
    ):
        return _contract_bundle_value_kt(contract)
    if clause == DiplomaticContract.CLAUSE_FLEET_BY_SHIP_COUNT:
        return _fleet_build_value_kt() * max(0, int(getattr(contract, 'request_ship_count', 0) or 0))
    if clause == DiplomaticContract.CLAUSE_SPECIFIC_FLEET:
        return _fleet_material_value_kt(getattr(contract, 'offer_fleet', None))
    if clause == DiplomaticContract.CLAUSE_SPECIFIC_COLONY:
        return _star_material_value_kt(getattr(contract, 'offer_star', None))
    return 0


def _contract_request_cost_kt(contract):
    from .models import DiplomaticContract

    if contract is None:
        return 0
    clause = str(getattr(contract, 'request_clause_type', '') or '')
    if clause == DiplomaticContract.CLAUSE_TECHNOLOGY:
        return _technology_clause_value_kt(contract, 'request')
    if clause == DiplomaticContract.CLAUSE_STANCE:
        return _stance_clause_value_kt(contract, 'request')
    if clause == DiplomaticContract.CLAUSE_REPORT:
        return _report_clause_value_kt(contract, 'request')
    if clause in (
        DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD,
        DiplomaticContract.CLAUSE_RESOURCE_ON_GIVEN_FLEET,
    ):
        return _contract_bundle_value_kt(contract)
    if clause == DiplomaticContract.CLAUSE_FLEET_BY_SHIP_COUNT:
        return _fleet_build_value_kt() * max(0, int(getattr(contract, 'request_ship_count', 0) or 0))
    if clause == DiplomaticContract.CLAUSE_SPECIFIC_COLONY:
        return _star_material_value_kt(getattr(contract, 'request_star', None))
    return 0


def _player_has_technology(player, technology):
    from .models import PlayerTechnologyGrant
    from .research import get_player_unlocked_technologies

    if not player or technology is None:
        return False
    if PlayerTechnologyGrant.objects.filter(player=player, technology=technology).exists():
        return True
    unlocked_ids = {
        int(getattr(item, 'id', 0) or 0)
        for item in get_player_unlocked_technologies(player)
    }
    return int(getattr(technology, 'id', 0) or 0) in unlocked_ids


def _repeat_request_count(contract):
    from .models import DiplomaticContract

    if contract is None:
        return 0
    return int(DiplomaticContract.objects.filter(
        game=contract.game,
        sender=contract.sender,
        recipient=contract.recipient,
        request_clause_type=contract.request_clause_type,
    ).exclude(id=contract.id).exclude(status=DiplomaticContract.STATUS_DRAFT).count())


def _repeat_chance_factor(repeat_count):
    count = max(0, int(repeat_count or 0))
    return 0.72 ** min(8, count)


def _ai_roll_acceptance(base_chance, repeat_count):
    chance = max(0.0, min(0.95, float(base_chance) * _repeat_chance_factor(repeat_count)))
    return random.random() < chance


def _interaction_recency_weight(age_years):
    age = max(0, int(age_years or 0))
    if age <= 30:
        return 1.0
    if age <= 60:
        return 0.6
    if age <= 90:
        return 0.3
    if age <= 150:
        return 0.1
    return 0.0


def _contract_resolution_year(contract, now_year):
    for field in ('handled_year', 'fulfilled_year', 'accepted_year', 'sent_year'):
        value = getattr(contract, field, None)
        try:
            year = int(value)
        except (TypeError, ValueError):
            continue
        if year > 0:
            return year
    return int(now_year or 0)


def _is_pure_gift_request(contract):
    from .models import DiplomaticContract

    if contract is None:
        return False
    request_clause = str(getattr(contract, 'request_clause_type', '') or '')
    offer_clause = str(getattr(contract, 'offer_clause_type', '') or '')
    if request_clause != DiplomaticContract.CLAUSE_NOTHING:
        return False
    if offer_clause in (
        DiplomaticContract.CLAUSE_NOTHING,
        DiplomaticContract.CLAUSE_VAGUE_THREAT,
    ):
        return False
    return True


def _directed_interaction_scores(sender, recipient, game, now_year):
    from .models import DiplomaticContract

    if sender is None or recipient is None or game is None:
        return {'success': 0.0, 'gift_success': 0.0, 'negative': 0.0}
    rows = DiplomaticContract.objects.filter(
        game=game,
        sender=sender,
        recipient=recipient,
    ).exclude(
        status__in=[DiplomaticContract.STATUS_DRAFT, DiplomaticContract.STATUS_SENT],
    )
    success = 0.0
    gift_success = 0.0
    negative = 0.0
    for row in rows:
        resolved_year = _contract_resolution_year(row, now_year)
        weight = _interaction_recency_weight(int(now_year or 0) - resolved_year)
        if weight <= 0.0:
            continue
        status = str(getattr(row, 'status', '') or '')
        if status in (
            DiplomaticContract.STATUS_ACCEPTED,
            DiplomaticContract.STATUS_FULFILLED,
        ):
            success += weight
            if _is_pure_gift_request(row):
                gift_success += weight
        elif status in (
            DiplomaticContract.STATUS_DECLINED,
            DiplomaticContract.STATUS_COUNTERED,
            DiplomaticContract.STATUS_EXPIRED,
            DiplomaticContract.STATUS_REVOKED,
        ):
            negative += weight
    return {
        'success': float(success),
        'gift_success': float(gift_success),
        'negative': float(negative),
    }


def _stance_rank(stance):
    value = str(stance or '').strip().upper()
    if value not in _STANCE_ORDER:
        value = 'NEUTRAL'
    return _STANCE_ORDER.index(value)


def _current_stance_towards_sender(recipient, sender):
    from .diplomacy import normalise_stance
    from .models import PlayerDiplomaticStance

    if recipient is None or sender is None:
        return 'NEUTRAL'
    row = PlayerDiplomaticStance.objects.filter(
        player=recipient,
        target_player=sender,
    ).first()
    if row is None:
        return 'NEUTRAL'
    return normalise_stance(
        getattr(row, 'pending_stance', '') or getattr(row, 'stance', 'NEUTRAL')
    )


def _next_higher_stance(current):
    value = str(current or '').strip().upper()
    if value not in _STANCE_ORDER:
        value = 'NEUTRAL'
    idx = _STANCE_ORDER.index(value)
    if idx >= len(_STANCE_ORDER) - 1:
        return _STANCE_ORDER[-1]
    return _STANCE_ORDER[idx + 1]


def _should_reject_unimplemented_delivery_clause(contract):
    from .models import DiplomaticContract

    clause = str(getattr(contract, 'request_clause_type', '') or '')
    return clause in (
        DiplomaticContract.CLAUSE_FLEET_BY_SHIP_COUNT,
        DiplomaticContract.CLAUSE_SPECIFIC_FLEET,
    )


def _technology_trade_has_new_offer(contract):
    from .models import DiplomaticContract

    if contract is None:
        return False
    if str(getattr(contract, 'request_clause_type', '') or '') != DiplomaticContract.CLAUSE_TECHNOLOGY:
        return False
    request_tech = getattr(contract, 'request_technology', None)
    offer_tech = getattr(contract, 'offer_technology', None)
    recipient = getattr(contract, 'recipient', None)
    sender = getattr(contract, 'sender', None)
    if request_tech is None or offer_tech is None:
        return False
    if not _player_has_technology(recipient, request_tech):
        return False
    if not _player_has_technology(sender, offer_tech):
        return False
    if _player_has_technology(recipient, offer_tech):
        return False
    return True


def _offered_technology_level_delta(contract, recipient):
    from .models import DiplomaticContract
    from .research import get_player_unlocked_technologies

    if contract is None or recipient is None:
        return 0
    if str(getattr(contract, 'offer_clause_type', '') or '') != DiplomaticContract.CLAUSE_TECHNOLOGY:
        return 0
    tech = getattr(contract, 'offer_technology', None)
    sender = getattr(contract, 'sender', None)
    if tech is None or sender is None:
        return 0
    if not _player_has_technology(sender, tech):
        return 0
    if _player_has_technology(recipient, tech):
        return 0
    category_id = int(getattr(tech, 'category_id', 0) or 0)
    highest = 0
    for unlocked in get_player_unlocked_technologies(recipient):
        if int(getattr(unlocked, 'category_id', 0) or 0) != category_id:
            continue
        try:
            level = int(getattr(unlocked, 'level', 0) or 0)
        except (TypeError, ValueError):
            level = 0
        if level > highest:
            highest = level
    try:
        offered_level = int(getattr(tech, 'level', 0) or 0)
    except (TypeError, ValueError):
        offered_level = 0
    return max(0, offered_level - highest)


def _is_offered_colony_habitable_for_recipient(contract):
    from .models import DiplomaticContract
    from .colony_rules import calculate_habitability_factor

    if contract is None:
        return False
    if str(getattr(contract, 'offer_clause_type', '') or '') != DiplomaticContract.CLAUSE_SPECIFIC_COLONY:
        return False
    star = getattr(contract, 'offer_star', None)
    recipient = getattr(contract, 'recipient', None)
    if star is None or recipient is None:
        return False
    return float(calculate_habitability_factor(recipient, star) or 0.0) > 0.0


def _is_new_technology_gift(contract, recipient):
    from .models import DiplomaticContract

    if contract is None or recipient is None:
        return False
    if str(getattr(contract, 'offer_clause_type', '') or '') != DiplomaticContract.CLAUSE_TECHNOLOGY:
        return False
    tech = getattr(contract, 'offer_technology', None)
    sender = getattr(contract, 'sender', None)
    if tech is None or sender is None:
        return False
    return (
        _player_has_technology(sender, tech) and
        not _player_has_technology(recipient, tech)
    )


def _mutual_stance_diplomacy_modifier(recipient, sender):
    from .diplomacy import STANCE_NEUTRAL, STANCE_SCORES, normalise_stance, stance_towards

    if recipient is None or sender is None:
        return 0.0
    recipient_stance = normalise_stance(stance_towards(recipient, sender))
    sender_stance = normalise_stance(stance_towards(sender, recipient))
    neutral_score = float(STANCE_SCORES.get(STANCE_NEUTRAL, 2))
    recipient_score = float(STANCE_SCORES.get(recipient_stance, neutral_score))
    sender_score = float(STANCE_SCORES.get(sender_stance, neutral_score))
    average_score = (recipient_score + sender_score) / 2.0
    return (average_score - neutral_score) * 0.06


def _clamped_acceptance_chance(value):
    return min(0.95, max(0.03, float(value or 0.0)))


def _trade_acceptance_chance(player, contract, request_value, offer_value, base=0.16):
    scores = _directed_interaction_scores(
        getattr(contract, 'sender', None),
        player,
        getattr(contract, 'game', None),
        int(getattr(getattr(contract, 'game', None), 'year', 0) or 0),
    )
    trust = max(0.0, float(scores.get('success', 0.0)) - (float(scores.get('negative', 0.0)) * 0.5))
    gift_success = max(0.0, float(scores.get('gift_success', 0.0) or 0.0))
    stance_modifier = _mutual_stance_diplomacy_modifier(player, getattr(contract, 'sender', None))
    ratio = 0.0
    if request_value > 0:
        ratio = float(max(0, offer_value)) / float(max(1, request_value))
    elif offer_value > 0:
        ratio = 1.25
    value_modifier = min(0.34, max(-0.24, (ratio - 1.0) * 0.24))
    trust_modifier = min(0.14, (trust * 0.04) + (gift_success * 0.03))
    return _clamped_acceptance_chance(base + value_modifier + stance_modifier + trust_modifier)


def _stance_exchange_acceptance_modifier(player, contract, requested_delta, scores):
    from .models import DiplomaticContract

    if contract is None or player is None or requested_delta <= 0:
        return 0.0
    if str(getattr(contract, 'offer_clause_type', '') or '') != DiplomaticContract.CLAUSE_STANCE:
        return 0.0
    sender = getattr(contract, 'sender', None)
    if sender is None:
        return 0.0
    requested = str(getattr(contract, 'request_stance', '') or '').strip().upper()
    offered = str(getattr(contract, 'offer_stance', '') or '').strip().upper()
    if not requested or not offered:
        return 0.0
    offered_current = _current_stance_towards_sender(sender, player)
    offered_delta = _stance_rank(offered) - _stance_rank(offered_current)
    if offered_delta <= 0:
        return 0.0

    trust = max(
        0.0,
        float(scores.get('success', 0.0)) - (float(scores.get('negative', 0.0)) * 0.5),
    )
    gift_success = max(0.0, float(scores.get('gift_success', 0.0) or 0.0))
    relationship_factor = min(1.0, (trust * 0.55) + (gift_success * 0.35))
    if relationship_factor <= 0.0:
        return 0.0

    boost = 0.0
    if requested == offered:
        boost += 0.05
    if offered_delta > requested_delta:
        boost += min(0.08, float(offered_delta - requested_delta) * 0.04)
    return min(0.10, boost * relationship_factor)


def _gift_offer_acceptance_chance(player, contract):
    from .models import DiplomaticContract

    clause = str(getattr(contract, 'offer_clause_type', '') or '')
    sender = getattr(contract, 'sender', None)
    scores = _directed_interaction_scores(
        sender,
        player,
        getattr(contract, 'game', None),
        int(getattr(getattr(contract, 'game', None), 'year', 0) or 0),
    )
    trust = max(0.0, float(scores.get('success', 0.0)) - (float(scores.get('negative', 0.0)) * 0.5))
    stance_modifier = _mutual_stance_diplomacy_modifier(player, sender)

    if clause == DiplomaticContract.CLAUSE_SPECIFIC_FLEET:
        return _clamped_acceptance_chance(0.82 + stance_modifier + min(0.10, trust * 0.04))
    if clause == DiplomaticContract.CLAUSE_TECHNOLOGY:
        delta = _offered_technology_level_delta(contract, player)
        # Technology gifts should be conservative at baseline, but ramp strongly
        # when they materially leapfrog the recipient's current tech level.
        base = 0.16 + min(0.56, float(delta) * 0.13)
        if _is_new_technology_gift(contract, player) and delta <= 0:
            base += 0.12
        return _clamped_acceptance_chance(base + stance_modifier + min(0.08, trust * 0.03))
    if clause == DiplomaticContract.CLAUSE_SPECIFIC_COLONY:
        base = 0.22
        if _is_offered_colony_habitable_for_recipient(contract):
            base = 0.74
        return _clamped_acceptance_chance(base + stance_modifier + min(0.06, trust * 0.02))
    if clause == DiplomaticContract.CLAUSE_REPORT:
        value = _contract_offer_value_kt(contract)
        base = 0.18
        if value >= 700:
            base = 0.50
        elif value >= 500:
            base = 0.38
        elif value >= 250:
            base = 0.30
        return _clamped_acceptance_chance(base + stance_modifier + min(0.08, trust * 0.03))
    if clause == DiplomaticContract.CLAUSE_STANCE:
        value = _contract_offer_value_kt(contract)
        base = 0.16 + min(0.30, float(value) / 1800.0)
        return _clamped_acceptance_chance(base + stance_modifier + min(0.08, trust * 0.03))
    if clause in (
        DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD,
        DiplomaticContract.CLAUSE_RESOURCE_ON_GIVEN_FLEET,
    ):
        return _clamped_acceptance_chance(0.72 + stance_modifier + min(0.10, trust * 0.04))
    return 0.0


_RESOURCE_DELIVERY_KEYS = (
    'ironium',
    'boranium',
    'germanium',
    'resource_x',
    'resource_y',
    'resource_z',
    'colonists',
)


def _resource_delivery_request_bundle(contract):
    if contract is None:
        return {}
    bundle = {}
    for key in _RESOURCE_DELIVERY_KEYS:
        amount = int(getattr(contract, 'request_%s' % key, 0) or 0)
        if amount > 0:
            bundle[key] = amount
    return bundle


def _resource_delivery_colony_reserve(key):
    if key in ('ironium', 'boranium', 'germanium'):
        return 50
    if key in ('resource_x', 'resource_y', 'resource_z'):
        return 10
    if key == 'colonists':
        return 20
    return 0


def _fleet_default_delivery_speed(fleet):
    try:
        safe_warp = int(getattr(fleet, 'max_safe_warp', 5) or 5)
    except (TypeError, ValueError):
        safe_warp = 5
    try:
        cloaked_warp = int(getattr(fleet, 'max_cloaked_warp', 0) or 0)
    except (TypeError, ValueError):
        cloaked_warp = 0
    speed = cloaked_warp if cloaked_warp > 0 else safe_warp
    return max(1, min(13, int(speed or 1)))


def _distance_years(x1, y1, x2, y2, speed):
    try:
        dx = float(x2) - float(x1)
        dy = float(y2) - float(y1)
    except (TypeError, ValueError):
        return 9999
    step = max(1, int(speed or 1))
    distance = math.sqrt((dx * dx) + (dy * dy))
    return int(math.ceil(distance / float(step)))


def _is_idle_fleet(fleet):
    if fleet is None:
        return False
    return not fleet.orders.exists()


def _fleet_remaining_capacity(fleet):
    capacity = int(getattr(fleet, 'cargo_capacity', 0) or 0)
    used = int(getattr(fleet, 'cargo_used', 0) or 0)
    return max(0, capacity - used)


def _fleet_requested_bundle_onboard(fleet, bundle):
    onboard = {}
    for key, needed in (bundle or {}).items():
        if key == 'colonists':
            amount = int(getattr(fleet, 'colonists', 0) or 0)
        else:
            amount = int(getattr(fleet, '%s_inventory' % key, 0) or 0)
        onboard[key] = min(max(0, amount), int(needed or 0))
    return onboard


def _star_available_for_bundle(star, bundle):
    if star is None:
        return {}
    available = {}
    for key, needed in (bundle or {}).items():
        reserve = _resource_delivery_colony_reserve(key)
        if key == 'colonists':
            raw = max(0, int(getattr(star, 'colonists', 0) or 0) // 1000)
        else:
            raw = max(0, int(getattr(star, '%s_inventory' % key, 0) or 0))
        available[key] = max(0, raw - reserve)
    return available


def _bundle_total(bundle):
    total = 0
    for key in _RESOURCE_DELIVERY_KEYS:
        total += max(0, int((bundle or {}).get(key, 0) or 0))
    return int(total)


def _remaining_contract_years(contract):
    if contract is None:
        return 0
    now = int(getattr(getattr(contract, 'game', None), 'year', 0) or 0)
    expires = int(getattr(contract, 'expires_year', 0) or 0)
    return max(0, (expires - now) + 1)


def _resource_to_world_destination_candidates(contract):
    sender = getattr(contract, 'sender', None)
    if sender is None:
        return []
    candidates = []
    suggested = getattr(contract, 'request_suggested_star', None)
    if (
        suggested is not None and
        int(getattr(suggested, 'game_id', 0) or 0) == int(getattr(contract, 'game_id', 0) or 0) and
        int(getattr(suggested, 'player_id', 0) or 0) == int(getattr(sender, 'id', 0) or 0)
    ):
        candidates.append(suggested)
    for star in sender.stars.filter(colonists__gt=0).order_by('-colonists', 'id'):
        if int(getattr(star, 'id', 0) or 0) in [int(getattr(item, 'id', 0) or 0) for item in candidates]:
            continue
        candidates.append(star)
    return candidates


def _plan_resource_to_world_delivery(player, contract):
    from .models import DiplomaticContract

    if contract is None:
        return None
    if str(getattr(contract, 'request_clause_type', '') or '') != DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD:
        return None
    request_bundle = _resource_delivery_request_bundle(contract)
    if not request_bundle:
        return None
    required_total = _bundle_total(request_bundle)
    if required_total <= 0:
        return None
    destination_candidates = _resource_to_world_destination_candidates(contract)
    if not destination_candidates:
        return None
    remaining_years = _remaining_contract_years(contract)
    if remaining_years <= 0:
        return None

    best = None
    for source in player.stars.filter(colonists__gt=0).order_by('-colonists', 'id'):
        available = _star_available_for_bundle(source, request_bundle)
        if any(int(available.get(key, 0) or 0) < int(amount or 0) for key, amount in request_bundle.items()):
            continue
        fleets = player.fleets.filter(x=source.x, y=source.y).order_by('-ship_count', 'id')
        for fleet in fleets:
            if not _is_idle_fleet(fleet):
                continue
            if _fleet_remaining_capacity(fleet) < required_total:
                continue
            speed = _fleet_default_delivery_speed(fleet)
            for destination in destination_candidates:
                travel_years = _distance_years(source.x, source.y, destination.x, destination.y, speed)
                eta_years = 2 + int(travel_years)
                if eta_years > remaining_years:
                    continue
                score = (
                    eta_years,
                    travel_years,
                    -int(getattr(fleet, 'ship_count', 0) or 0),
                    str(getattr(fleet, 'id', '') or ''),
                )
                if best is None or score < best['score']:
                    best = {
                        'score': score,
                        'kind': 'resource_to_world',
                        'fleet_id': str(fleet.id),
                        'source_star_id': str(source.id),
                        'destination_star_id': str(destination.id),
                        'bundle': dict(request_bundle),
                        'speed': int(speed),
                    }
    return best


def _plan_resource_on_given_fleet_delivery(player, contract):
    from .models import DiplomaticContract

    if contract is None:
        return None
    if str(getattr(contract, 'request_clause_type', '') or '') != DiplomaticContract.CLAUSE_RESOURCE_ON_GIVEN_FLEET:
        return None
    request_bundle = _resource_delivery_request_bundle(contract)
    if not request_bundle:
        return None
    remaining_years = _remaining_contract_years(contract)
    if remaining_years <= 0:
        return None

    best = None
    for source in player.stars.filter(colonists__gt=0).order_by('-colonists', 'id'):
        fleets = player.fleets.filter(x=source.x, y=source.y).order_by('-ship_count', 'id')
        for fleet in fleets:
            if not _is_idle_fleet(fleet):
                continue
            if int(getattr(fleet, 'ship_count', 0) or 0) <= 0:
                continue
            onboard = _fleet_requested_bundle_onboard(fleet, request_bundle)
            required_load = {}
            for key, amount in request_bundle.items():
                required_load[key] = max(0, int(amount or 0) - int(onboard.get(key, 0) or 0))
            if _fleet_remaining_capacity(fleet) < _bundle_total(required_load):
                continue
            available = _star_available_for_bundle(source, required_load)
            if any(int(available.get(key, 0) or 0) < int(amount or 0) for key, amount in required_load.items()):
                continue
            score = (
                1,
                -int(getattr(fleet, 'ship_count', 0) or 0),
                str(getattr(fleet, 'id', '') or ''),
            )
            if best is None or score < best['score']:
                best = {
                    'score': score,
                    'kind': 'resource_on_given_fleet',
                    'fleet_id': str(fleet.id),
                    'source_star_id': str(source.id),
                    'required_load': dict(required_load),
                    'speed': int(_fleet_default_delivery_speed(fleet)),
                }
    return best


def _plan_resource_delivery_contract(player, contract, module_code):
    from .models import DiplomaticContract

    if not ai_module_uses_micromanager_behavior(module_code):
        return None
    clause = str(getattr(contract, 'request_clause_type', '') or '')
    if clause == DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD:
        return _plan_resource_to_world_delivery(player, contract)
    if clause == DiplomaticContract.CLAUSE_RESOURCE_ON_GIVEN_FLEET:
        return _plan_resource_on_given_fleet_delivery(player, contract)
    return None


def _queue_transfer_order_to_star(game, fleet, star, transfer_type, transfer_bundle):
    from .models import FleetOrders

    kwargs = {
        'game': game,
        'fleet': fleet,
        'order_type': 'TRANSFER',
        'repeat': False,
        'transfer_type': transfer_type,
        'transfer_ironium': int((transfer_bundle or {}).get('ironium', 0) or 0),
        'transfer_boranium': int((transfer_bundle or {}).get('boranium', 0) or 0),
        'transfer_germanium': int((transfer_bundle or {}).get('germanium', 0) or 0),
        'transfer_resource_x': int((transfer_bundle or {}).get('resource_x', 0) or 0),
        'transfer_resource_y': int((transfer_bundle or {}).get('resource_y', 0) or 0),
        'transfer_resource_z': int((transfer_bundle or {}).get('resource_z', 0) or 0),
        'transfer_colonists': int((transfer_bundle or {}).get('colonists', 0) or 0),
        'target_star': star,
        'target_kind': 'OBJECT',
        'target_short_id': star.short_id,
        'x': int(star.x),
        'y': int(star.y),
        'added_by_micromanager': True,
    }
    FleetOrders.objects.create(**kwargs)


def _queue_move_order_to_star(game, fleet, star, speed):
    from .models import FleetOrders

    warp = max(1, min(13, int(speed or 1)))
    FleetOrders.objects.create(
        game=game,
        fleet=fleet,
        order_type='MOVE',
        repeat=False,
        warpfactor=warp,
        original_warpfactor=warp,
        overmax_risk_checked=False,
        target_star=star,
        target_kind='OBJECT',
        target_short_id=star.short_id,
        x=int(star.x),
        y=int(star.y),
        added_by_micromanager=True,
    )


def _queue_resource_delivery_plan(player, contract, plan):
    from .models import Fleet, Star, FleetOrders

    if player is None or contract is None or not isinstance(plan, dict):
        return False
    fleet = Fleet.objects.filter(
        id=str(plan.get('fleet_id') or ''),
        game=player.game,
        player=player,
    ).first()
    if fleet is None:
        return False
    if not _is_idle_fleet(fleet):
        return False

    kind = str(plan.get('kind') or '')
    if kind == 'resource_to_world':
        source = Star.objects.filter(
            id=str(plan.get('source_star_id') or ''),
            game=player.game,
            player=player,
        ).first()
        destination = Star.objects.filter(
            id=str(plan.get('destination_star_id') or ''),
            game=player.game,
            player=getattr(contract, 'sender', None),
        ).first()
        if source is None or destination is None:
            return False
        bundle = dict(plan.get('bundle') or {})
        if _bundle_total(bundle) <= 0:
            return False
        _queue_transfer_order_to_star(player.game, fleet, source, 'LOAD', bundle)
        if int(source.x) != int(destination.x) or int(source.y) != int(destination.y):
            _queue_move_order_to_star(player.game, fleet, destination, int(plan.get('speed', 1) or 1))
        _queue_transfer_order_to_star(player.game, fleet, destination, 'UNLOAD', bundle)
        return True

    if kind == 'resource_on_given_fleet':
        source = Star.objects.filter(
            id=str(plan.get('source_star_id') or ''),
            game=player.game,
            player=player,
        ).first()
        if source is None:
            return False
        load_bundle = dict(plan.get('required_load') or {})
        if _bundle_total(load_bundle) > 0:
            _queue_transfer_order_to_star(player.game, fleet, source, 'LOAD', load_bundle)
        FleetOrders.objects.create(
            game=player.game,
            fleet=fleet,
            order_type='GIVE',
            repeat=False,
            transfer_player=getattr(contract, 'sender', None),
            added_by_micromanager=True,
        )
        return True
    return False


def _next_lower_stance(current):
    value = str(current or '').strip().upper()
    if value not in _STANCE_ORDER:
        value = 'NEUTRAL'
    idx = _STANCE_ORDER.index(value)
    if idx <= 0:
        return _STANCE_ORDER[0]
    return _STANCE_ORDER[idx - 1]


def _maybe_downgrade_stance_after_rejection(contract):
    from .diplomacy import ensure_contact_stance_entry, normalise_stance
    from .models import DiplomaticContract

    if contract is None:
        return False
    declines = int(DiplomaticContract.objects.filter(
        game=contract.game,
        sender=contract.sender,
        recipient=contract.recipient,
        status=DiplomaticContract.STATUS_DECLINED,
    ).count())
    if declines < 2:
        return False
    row = ensure_contact_stance_entry(contract.recipient, contract.sender)
    if row is None:
        return False
    current = normalise_stance(getattr(row, 'pending_stance', '') or getattr(row, 'stance', 'NEUTRAL'))
    lowered = _next_lower_stance(current)
    if lowered == current:
        return False
    row.pending_stance = lowered
    row.save(update_fields=['pending_stance'])
    return True


def _maybe_upgrade_stance_after_accepted_gift(contract):
    from .diplomacy import ensure_contact_stance_entry, normalise_stance
    from .models import DiplomaticContract

    if contract is None or not _is_pure_gift_request(contract):
        return False
    if str(getattr(contract, 'status', '') or '') not in (
        DiplomaticContract.STATUS_ACCEPTED,
        DiplomaticContract.STATUS_FULFILLED,
    ):
        return False
    sender = getattr(contract, 'sender', None)
    recipient = getattr(contract, 'recipient', None)
    game = getattr(contract, 'game', None)
    if sender is None or recipient is None or game is None:
        return False
    latest = DiplomaticContract.objects.filter(
        game=game,
        sender=sender,
        recipient=recipient,
    ).exclude(status=DiplomaticContract.STATUS_DRAFT).order_by('-sent_year', '-id').first()
    # Only evaluate stance upgrades on completion of the most recent request.
    if latest is None or int(getattr(latest, 'id', 0) or 0) != int(getattr(contract, 'id', 0) or 0):
        return False
    scores = _directed_interaction_scores(
        sender,
        recipient,
        game,
        int(getattr(game, 'year', 0) or 0),
    )
    # Require multiple successful gifts in the recency-weighted window.
    if float(scores.get('gift_success', 0.0)) < 1.8:
        return False
    row = ensure_contact_stance_entry(recipient, sender)
    if row is None:
        return False
    current = normalise_stance(
        getattr(row, 'pending_stance', '') or getattr(row, 'stance', 'NEUTRAL')
    )
    raised = _next_higher_stance(current)
    if raised == current:
        return False
    row.pending_stance = raised
    row.save(update_fields=['pending_stance'])
    return True


def _decide_passive_ai_contract_response(player, contract, module_code):
    from .models import DiplomaticContract

    if _should_reject_unimplemented_delivery_clause(contract):
        return False, 'delivery-not-implemented', None

    if (
        str(getattr(contract, 'request_clause_type', '') or '') == DiplomaticContract.CLAUSE_SPECIFIC_COLONY and
        int(getattr(contract, 'request_star_id', 0) or 0) == int(getattr(player, 'homeworld_id', 0) or 0)
    ):
        return False, 'homeworld-protected', None

    offer_value = _contract_offer_value_kt(contract)
    request_value = _contract_request_cost_kt(contract)
    repeat_count = _repeat_request_count(contract)
    scores = _directed_interaction_scores(
        getattr(contract, 'sender', None),
        player,
        getattr(contract, 'game', None),
        int(getattr(getattr(contract, 'game', None), 'year', 0) or 0),
    )
    trust = max(0.0, float(scores.get('success', 0.0)) - (float(scores.get('negative', 0.0)) * 0.5))

    request_clause = str(getattr(contract, 'request_clause_type', '') or '')
    if (
        ai_module_uses_micromanager_behavior(module_code) and
        _is_pure_gift_request(contract)
    ):
        gift_base = _gift_offer_acceptance_chance(player, contract)
        if gift_base > 0.0:
            return _ai_roll_acceptance(gift_base, repeat_count), 'pure-gift-roll', None

    if request_clause in (
        DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD,
        DiplomaticContract.CLAUSE_RESOURCE_ON_GIVEN_FLEET,
    ):
        if not ai_module_uses_micromanager_behavior(module_code):
            return False, 'delivery-not-implemented', None
        plan = _plan_resource_delivery_contract(player, contract, module_code)
        if not isinstance(plan, dict):
            return False, 'resource-delivery-not-feasible', None
        if request_value <= 0:
            return False, 'resource-delivery-invalid-request', None
        if offer_value <= 0:
            return False, 'resource-delivery-no-reward', None
        ratio = float(offer_value) / float(max(1, request_value))
        if ratio < 0.85:
            return False, 'resource-delivery-unfavorable', None
        reward_base = _gift_offer_acceptance_chance(player, contract)
        if reward_base <= 0.0:
            reward_base = 0.22
        base = reward_base * min(1.35, max(0.45, ratio))
        base += min(0.04, trust * 0.01)
        if offer_value > request_value:
            base += 0.04
        return _ai_roll_acceptance(base, repeat_count), 'resource-delivery-roll', plan

    if request_clause == DiplomaticContract.CLAUSE_TECHNOLOGY:
        if not _technology_trade_has_new_offer(contract):
            return False, 'technology-trade-invalid', None
        base = 0.10 if module_code == AI_MODULE_IDLE else 0.20
        chance = _trade_acceptance_chance(player, contract, request_value, offer_value, base=base)
        chance += min(0.18, float(_offered_technology_level_delta(contract, player)) * 0.03)
        return _ai_roll_acceptance(_clamped_acceptance_chance(chance), repeat_count), 'technology-trade-roll', None

    if request_clause == DiplomaticContract.CLAUSE_STANCE:
        if module_code == AI_MODULE_IDLE:
            base = 0.04
            chance = _trade_acceptance_chance(player, contract, request_value, offer_value, base=base)
            return _ai_roll_acceptance(chance, repeat_count), 'stance-roll-idle', None

        requested = str(getattr(contract, 'request_stance', '') or '').strip().upper()
        current = _current_stance_towards_sender(player, getattr(contract, 'sender', None))
        delta = _stance_rank(requested) - _stance_rank(current)
        offer_clause = str(getattr(contract, 'offer_clause_type', '') or '')
        if offer_clause == DiplomaticContract.CLAUSE_STANCE:
            if delta < 0:
                base = 0.68
            elif delta == 0:
                base = 0.40
            elif delta == 1:
                base = 0.12 + min(0.45, (trust * 0.22) + (float(scores.get('gift_success', 0.0)) * 0.08))
            else:
                base = 0.04 + min(0.20, trust * 0.08)
        else:
            if delta < 0:
                base = 0.45
            elif delta == 0:
                base = 0.22
            elif delta == 1:
                base = 0.08 + min(0.25, trust * 0.12)
            else:
                base = 0.03
        chance = _trade_acceptance_chance(player, contract, request_value, offer_value, base=base)
        chance += _stance_exchange_acceptance_modifier(player, contract, delta, scores)
        return _ai_roll_acceptance(_clamped_acceptance_chance(chance), repeat_count), 'stance-roll-micromanager', None

    if request_clause == DiplomaticContract.CLAUSE_REPORT:
        if request_value <= 0:
            return False, 'report-trade-invalid', None
        base = 0.18
        if str(getattr(contract, 'offer_clause_type', '') or '') == DiplomaticContract.CLAUSE_REPORT:
            base = 0.24
        chance = _trade_acceptance_chance(player, contract, request_value, offer_value, base=base)
        return _ai_roll_acceptance(chance, repeat_count), 'report-trade-roll', None

    if request_clause == DiplomaticContract.CLAUSE_SPECIFIC_COLONY:
        if request_value <= 0:
            return False, 'colony-trade-invalid', None
        if offer_value <= 0:
            return False, 'colony-trade-no-offer', None
        chance = _trade_acceptance_chance(player, contract, request_value, offer_value, base=0.08)
        return _ai_roll_acceptance(chance, repeat_count), 'colony-trade-roll', None

    if module_code == AI_MODULE_IDLE:
        if offer_value <= 0:
            return False, 'idle-requires-material-offer', None
        if request_value > 0 and offer_value <= request_value:
            return False, 'idle-unfavorable', None
        chance = _trade_acceptance_chance(player, contract, request_value, offer_value, base=0.08)
        return _ai_roll_acceptance(chance, repeat_count), 'idle-material-roll', None

    if request_value > 0:
        if offer_value <= 0:
            return False, 'trade-no-offer', None
        chance = _trade_acceptance_chance(player, contract, request_value, offer_value, base=0.14)
        return _ai_roll_acceptance(chance, repeat_count), 'trade-roll', None
    if offer_value > 0:
        chance = _gift_offer_acceptance_chance(player, contract)
        if chance <= 0.0:
            chance = _trade_acceptance_chance(player, contract, request_value, offer_value, base=0.18)
        return _ai_roll_acceptance(chance, repeat_count), 'free-offer-roll', None
    return False, 'default-reject', None


def _apply_passive_ai_diplomacy_turn(player, game, module_code):
    from .diplomatic_contracts import list_player_contracts, perform_contract_action
    from .models import DiplomaticContract

    contracts = list_player_contracts(
        player,
        status='sent',
        direction='incoming',
        oldest_first=True,
    )
    accepted = 0
    declined = 0
    downgraded_senders = set()
    upgraded_senders = set()
    for contract in contracts:
        should_accept, _reason, delivery_plan = _decide_passive_ai_contract_response(
            player,
            contract,
            module_code,
        )
        if should_accept:
            ok, _msg = perform_contract_action(
                contract,
                player,
                'accept',
                ignore_action_lock=True,
            )
            if ok:
                contract.refresh_from_db()
                if isinstance(delivery_plan, dict):
                    _queue_resource_delivery_plan(player, contract, delivery_plan)
                accepted += 1
                sender_id = int(getattr(contract, 'sender_id', 0) or 0)
                if (
                    ai_module_uses_micromanager_behavior(module_code) and
                    sender_id and
                    sender_id not in upgraded_senders
                ):
                    if _maybe_upgrade_stance_after_accepted_gift(contract):
                        upgraded_senders.add(sender_id)
                continue
            contract.refresh_from_db()
            if contract.status != DiplomaticContract.STATUS_SENT:
                continue
        ok, _msg = perform_contract_action(
            contract,
            player,
            'decline',
            ignore_action_lock=True,
        )
        if not ok:
            continue
        declined += 1
        sender_id = int(getattr(contract, 'sender_id', 0) or 0)
        if sender_id and sender_id not in downgraded_senders:
            if _maybe_downgrade_stance_after_rejection(contract):
                downgraded_senders.add(sender_id)
    return {
        'accepted': int(accepted),
        'declined': int(declined),
    }


def _apply_openai_module_turn(player, game):
    config = get_ai_module_config(AI_MODULE_OPENAI)
    max_iterations = _bounded_int(config.get('max_iterations'), 6, 1, 40)
    max_history_chars = _bounded_int(config.get('history_chars'), 18000, 4000, 100000)
    step_output_chars = _bounded_int(config.get('step_output_chars'), 2600, 300, 12000)

    system_prompt = _build_openai_system_prompt(game, player, config)
    snapshot = _build_openai_state_snapshot(game, player, config)
    if not snapshot:
        snapshot = 'No snapshot data available.'

    messages = [
        {'role': 'system', 'content': system_prompt},
        {
            'role': 'user',
            'content': (
                'Initial game snapshot follows.\n\n%s\n\n'
                'Choose your next command and respond as JSON.'
            ) % snapshot,
        },
    ]

    commands_executed = 0
    iterations_used = 0
    last_note = ''
    for _ in range(max_iterations):
        iterations_used += 1
        _trim_messages(messages, max_history_chars)
        response_text = _openai_chat_completion(config, messages)
        decision = _extract_ai_decision(response_text)
        command = str(decision.get('command') or '').strip()
        done = bool(decision.get('done', False))
        note = str(decision.get('note') or '').strip()
        if note:
            last_note = note
        if done:
            break
        if not command:
            messages.append({'role': 'assistant', 'content': response_text})
            messages.append({
                'role': 'user',
                'content': (
                    'No command was detected. Reply with JSON like '
                    '{"command":"/status","done":false}.'
                ),
            })
            continue
        if not _is_valid_ai_cli_command(command):
            messages.append({'role': 'assistant', 'content': response_text})
            messages.append({
                'role': 'user',
                'content': (
                    'That command is not valid in browser Play CLI. '
                    'Use a valid command and return JSON only.'
                ),
            })
            continue
        command_output = _execute_play_cli_command(game, player, command)
        commands_executed += 1
        messages.append({
            'role': 'assistant',
            'content': json.dumps({
                'command': command,
                'done': False,
                'note': note,
            }),
        })
        messages.append({
            'role': 'user',
            'content': (
                'Command output for %s:\n%s\n\n'
                'Choose the next command, or set {"done":true} when finished.'
            ) % (command, _truncate_text(command_output, step_output_chars)),
        })

    return {
        'ok': True,
        'module': AI_MODULE_OPENAI,
        'iterations_used': int(iterations_used),
        'commands_executed': int(commands_executed),
        'last_note': last_note,
    }


def apply_ai_module_turn(player, game):
    if not player or not bool(getattr(player, 'is_ai', False)):
        return {'ok': False, 'skipped': True, 'reason': 'not-ai-player'}
    module_code = normalize_ai_module_code(getattr(player, 'ai_module', ''))
    if not module_code:
        return {'ok': False, 'skipped': True, 'reason': 'missing-module'}
    if not is_ai_module_enabled(module_code):
        return {'ok': False, 'skipped': True, 'reason': 'module-disabled'}

    if module_code == AI_MODULE_OPENAI:
        try:
            return _apply_openai_module_turn(player, game)
        except Exception:
            logger.exception(
                'AI OpenAI-compatible module failed for player=%s game=%s',
                getattr(player, 'short_id', None),
                getattr(game, 'short_id', None),
            )
            return {'ok': False, 'skipped': True, 'reason': 'module-error'}

    # Passive modules still perform diplomacy response checks during AI check-ins.
    diplomacy = _apply_passive_ai_diplomacy_turn(player, game, module_code)
    return {
        'ok': True,
        'skipped': True,
        'reason': 'passive-module',
        'diplomacy': diplomacy,
    }


def count_active_ai_players(server_capped_only=False):
    from .models import Player

    qs = Player.objects.filter(
        is_ai=True,
        defeated=False,
        game__ended=False,
    )
    if not server_capped_only:
        return qs.count()
    return qs.exclude(ai_module__in=list(AI_SERVER_CAP_EXCLUDED_MODULES)).count()


def get_remaining_server_ai_capacity():
    max_server = get_ai_max_per_server()
    if max_server <= 0:
        return 0
    return max(0, max_server - count_active_ai_players(server_capped_only=True))


def get_create_game_ai_capacity():
    max_game = get_ai_max_per_game()
    if max_game <= 0:
        return 0
    return max_game
