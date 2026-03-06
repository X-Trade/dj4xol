import shlex

from django.core.cache import cache
from django.core.management.base import CommandError

from dj4xol.management.commands.play import Command as PlayCommand

MAX_COMMAND_LENGTH = 256
RATE_LIMIT_WINDOW_SECONDS = 10
RATE_LIMIT_BURST = 30


class _TranscriptCollector:
    def __init__(self):
        self.lines = []

    def write(self, msg="", style_func=None, ending="\n"):
        text = "" if msg is None else str(msg)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if text == "":
            self.lines.append("")
            return
        self.lines.extend(text.split("\n"))


def build_bootstrap_transcript(game, player):
    collector = _TranscriptCollector()
    collector.write(
        "Connected: game=%s year=%s player=%s (%s)"
        % (game.short_id, game.year, player.name, player.short_id)
    )
    runner = _build_runner(collector)
    runner._show_priority_messages(player, game)
    collector.write("Type /help for available commands.")
    return collector.lines


def execute_browser_command(game, player, raw_command):
    raw_command = _normalise_command(raw_command)
    command_parts = _parse_command_parts(raw_command)
    if raw_command in ("/exit", "/quit"):
        return {
            "ok": True,
            "lines": ["Disconnected."],
            "close_overlay": True,
            "mutated": False,
        }
    if not _is_allowed_browser_command(raw_command):
        return {
            "ok": False,
            "lines": ["Web Play CLI does not support that command."],
            "close_overlay": False,
            "mutated": False,
        }

    collector = _TranscriptCollector()
    runner = _build_runner(collector)
    try:
        runner._execute_cli_command(raw_command, player, game)
    except CommandError as exc:
        collector.write(str(exc))
        return {
            "ok": False,
            "lines": collector.lines,
            "close_overlay": False,
            "mutated": False,
        }
    result = {
        "ok": True,
        "lines": collector.lines,
        "close_overlay": False,
        "mutated": _is_mutating_browser_command(command_parts),
    }
    navigate_to = _detail_navigation_payload(runner, player, command_parts)
    if navigate_to is not None:
        result["navigate_to"] = navigate_to
    return result


def enforce_browser_rate_limit(game, account):
    bucket = _rate_limit_bucket_key(game, account)
    count = cache.get(bucket, 0)
    count = int(count or 0) + 1
    cache.set(bucket, count, RATE_LIMIT_WINDOW_SECONDS)
    return count <= RATE_LIMIT_BURST


def _build_runner(collector):
    runner = PlayCommand()
    runner.stdout = collector
    return runner


def _normalise_command(raw_command):
    command = (raw_command or "").strip()
    if not command:
        raise CommandError("Command is required.")
    if len(command) > MAX_COMMAND_LENGTH:
        raise CommandError("Command is too long.")
    if "\n" in command or "\r" in command or "\x00" in command:
        raise CommandError("Invalid command.")
    return command


def _is_allowed_browser_command(raw_command):
    parts = _parse_command_parts(raw_command)
    if parts is None:
        return False
    if not parts:
        return False
    if _is_browser_help_command(parts):
        return True

    command = parts[0].lower()
    if command in (
        "/help",
        "/status",
        "/reports",
        "/colonies",
        "/stars",
        "/anomalies",
        "/salvage",
        "/exit",
        "/quit",
    ):
        return len(parts) == 1
    if command == "/fleets":
        return len(parts) == 1 or (len(parts) == 2 and parts[1].lower() in ("own", "other", "all"))
    if command == "/detail":
        return len(parts) == 2
    if command == "/messages":
        return True
    if command == "/orders":
        if len(parts) == 2:
            return True
        if len(parts) == 3 and parts[2].lower() in ("list", "clear", "add"):
            return True
        if len(parts) >= 4 and parts[2].lower() == "add":
            return True
        return False
    if command == "/research":
        return len(parts) in (1, 2, 3)
    if command == "/rename":
        return len(parts) >= 3
    if command == "/notes":
        if len(parts) == 1:
            return True
        if parts[1].lower() == "add":
            return len(parts) >= 3
        if parts[1].lower() == "remove":
            return len(parts) == 3
        return False
    return False


def _is_browser_help_command(parts):
    if not parts:
        return False
    command = parts[0].lower()
    if command == "/help":
        return len(parts) <= 3
    if len(parts) == 2 and parts[1].lower() == "help":
        return True
    if len(parts) == 3 and parts[2].lower() == "help":
        return True
    return False


def _is_mutating_browser_command(parts):
    if not parts:
        return False
    command = parts[0].lower()
    if command == "/rename":
        return len(parts) >= 3
    if command == "/notes":
        return len(parts) >= 2 and parts[1].lower() in ("add", "remove")
    if command == "/orders":
        return (
            len(parts) >= 3 and
            parts[2].lower() in ("clear", "add") and
            not _is_browser_help_command(parts)
        )
    if command == "/research":
        return len(parts) == 3
    return False


def _rate_limit_bucket_key(game, account):
    return "play_cli_web:%s:%s" % (game.id, account.pk)


def _parse_command_parts(raw_command):
    try:
        return shlex.split(raw_command)
    except ValueError:
        return None


def _detail_navigation_payload(runner, player, command_parts):
    if not command_parts or len(command_parts) != 2:
        return None
    if command_parts[0].lower() != "/detail":
        return None
    try:
        obj = runner._resolve_detail_object(player, command_parts[1])
    except CommandError:
        return None
    if obj is None:
        return None
    return {
        "sel": obj.short_id,
        "x": int(obj.x),
        "y": int(obj.y),
        "locate": True,
    }
