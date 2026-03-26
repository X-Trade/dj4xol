from __future__ import unicode_literals

import json
import logging
import os
import random
import urllib.error
import urllib.request

from .models import ServerSettings, server_setting_enabled, server_setting_int


AI_MODULE_MICROMANAGER = 'micromanager'
AI_MODULE_IDLE = 'idle'
AI_MODULE_OPENAI = 'openai'
AI_SLOT_RANDOM_RACE = '__RANDOM__'
AI_SLOT_RANDOM_STANCE = 'RANDOM'
AI_RANDOM_STANCE_POOL = ('HOSTILE', 'COLD', 'NEUTRAL', 'WARM')

logger = logging.getLogger(__name__)

AI_MODULE_ORDER = (
    AI_MODULE_MICROMANAGER,
    AI_MODULE_IDLE,
    AI_MODULE_OPENAI,
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


def _contract_offer_value_kt(contract):
    from .models import DiplomaticContract

    if contract is None:
        return 0
    clause = str(getattr(contract, 'offer_clause_type', '') or '')
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


def _should_reject_unimplemented_delivery_clause(contract):
    from .models import DiplomaticContract

    clause = str(getattr(contract, 'request_clause_type', '') or '')
    return clause in (
        DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD,
        DiplomaticContract.CLAUSE_RESOURCE_ON_GIVEN_FLEET,
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


def _decide_passive_ai_contract_response(player, contract, module_code):
    from .models import DiplomaticContract

    if _should_reject_unimplemented_delivery_clause(contract):
        return False, 'delivery-not-implemented'

    if (
        str(getattr(contract, 'request_clause_type', '') or '') == DiplomaticContract.CLAUSE_SPECIFIC_COLONY and
        int(getattr(contract, 'request_star_id', 0) or 0) == int(getattr(player, 'homeworld_id', 0) or 0)
    ):
        return False, 'homeworld-protected'

    offer_value = _contract_offer_value_kt(contract)
    request_value = _contract_request_cost_kt(contract)
    repeat_count = _repeat_request_count(contract)

    request_clause = str(getattr(contract, 'request_clause_type', '') or '')
    if request_clause == DiplomaticContract.CLAUSE_TECHNOLOGY:
        if not _technology_trade_has_new_offer(contract):
            return False, 'technology-trade-invalid'
        base = 0.10 if module_code == AI_MODULE_IDLE else 0.20
        if offer_value > request_value:
            base += 0.05
        return _ai_roll_acceptance(base, repeat_count), 'technology-trade-roll'

    if request_clause == DiplomaticContract.CLAUSE_STANCE:
        base = 0.04 if module_code == AI_MODULE_IDLE else 0.10
        if offer_value > request_value:
            base += 0.04
        return _ai_roll_acceptance(base, repeat_count), 'stance-roll'

    if module_code == AI_MODULE_IDLE:
        if offer_value <= 0:
            return False, 'idle-requires-material-offer'
        if request_value > 0 and offer_value <= request_value:
            return False, 'idle-unfavorable'
        return True, 'idle-material-accept'

    if request_value > 0:
        if offer_value <= request_value:
            return False, 'unfavorable-trade'
        return True, 'favorable-trade'
    if offer_value > 0:
        return True, 'free-material-offer'
    return False, 'default-reject'


def _apply_passive_ai_diplomacy_turn(player, game, module_code):
    from .diplomatic_contracts import accept_contract, decline_contract
    from .models import DiplomaticContract

    contracts = list(
        DiplomaticContract.objects.filter(
            game=game,
            recipient=player,
            status=DiplomaticContract.STATUS_SENT,
        ).select_related(
            'sender',
            'recipient',
            'request_technology',
            'offer_technology',
            'offer_fleet',
            'request_star',
            'offer_star',
        ).order_by('sent_year', 'created_at', 'id')
    )
    accepted = 0
    declined = 0
    downgraded_senders = set()
    for contract in contracts:
        should_accept, _reason = _decide_passive_ai_contract_response(
            player,
            contract,
            module_code,
        )
        if should_accept:
            ok, _msg = accept_contract(contract, player)
            if ok:
                accepted += 1
                continue
            contract.refresh_from_db()
            if contract.status != DiplomaticContract.STATUS_SENT:
                continue
        ok, _msg = decline_contract(contract, player)
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
