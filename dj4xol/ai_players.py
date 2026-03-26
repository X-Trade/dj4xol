from __future__ import unicode_literals

import json
import logging
import os
import urllib.error
import urllib.request

from .models import ServerSettings, server_setting_enabled, server_setting_int


AI_MODULE_MICROMANAGER = 'micromanager'
AI_MODULE_IDLE = 'idle'
AI_MODULE_OPENAI = 'openai'

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

    # Other modules currently rely on passive administration-tier behavior.
    return {'ok': True, 'skipped': True, 'reason': 'passive-module'}


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
