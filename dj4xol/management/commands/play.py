import getpass
import html
import os
import re
import shlex
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import authenticate
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max, Q
from django.utils import timezone

from dj4xol.models import (
    Account,
    Anomaly,
    Fleet,
    FleetOrders,
    Game,
    Player,
    PlayerNote,
    PRODUCTION_COSTS,
    ProductionOrder,
    ResearchCategory,
    Report,
    Salvage,
    Star,
)
from dj4xol.mineral_rules import ALL_RESOURCE_KEYS, SECRET_RESOURCE_KEYS, known_resource_keys
from dj4xol.colony_rules import calculate_habitability_factor
from dj4xol.objectdetails import DetailBuilder
from dj4xol.research import (
    build_research_budget,
    build_research_screen_data,
    ensure_player_research_rows,
    get_player_available_production_orders,
    set_singular_allocation,
    update_player_allocations,
)
from dj4xol.turn import GameTurn

try:  # Enables terminal history/editing for input() on supported platforms.
    import readline  # noqa: F401
except Exception:  # pragma: no cover - platform dependent
    readline = None

try:
    import yaml
except Exception:  # pragma: no cover - fallback should be rare
    yaml = None


class Command(BaseCommand):
    help = "Interactive CLI for playing a game as a player."
    HISTORY_PATH = os.path.expanduser("~/.dj4xol_play_history")
    HISTORY_LENGTH = 500
    SHORT_ID_RE = re.compile(r"^[0-9a-z]{12}$")
    HTML_LINK_RE = re.compile(
        r'<a\s+[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<label>.*?)</a>',
        re.IGNORECASE,
    )
    HTML_TAG_RE = re.compile(r"<[^>]+>")
    CLI_SHORT_ID_TOKEN = "__DJ4XOL_SHORT_ID__%s__"

    def add_arguments(self, parser):
        parser.add_argument("game_short_id", help="Game short_id (e.g. abcdef66)")
        parser.add_argument(
            "--user",
            dest="username",
            help="Django username for authentication (prompted if omitted).",
        )
        parser.add_argument(
            "--player",
            dest="player_selector",
            help="Player selector (short_id or exact player name).",
        )
        parser.add_argument(
            "--account",
            dest="account_selector",
            help="Account selector (alias or username).",
        )
        parser.add_argument(
            "--no-auth",
            action="store_true",
            help="Skip username/password authentication (local trusted use).",
        )
        parser.add_argument(
            "-c",
            "--command",
            dest="one_shot_command",
            help="Execute one CLI command and exit (non-interactive).",
        )

    def handle(self, *args, **options):
        game = self._get_game(options["game_short_id"])
        user = None
        account = None
        if not options["no_auth"]:
            user = self._authenticate_user(options.get("username"))
            account = getattr(user, "dj4xol_account", None)
            if account is None:
                raise CommandError("Authenticated user has no dj4xol account.")

        player = self._resolve_player(
            game=game,
            account=account,
            user=user,
            player_selector=options.get("player_selector"),
            account_selector=options.get("account_selector"),
            no_auth=bool(options["no_auth"]),
        )
        if bool(getattr(player, "defeated", False)):
            self.stdout.write(self.style.ERROR(
                "Game Over: your homeworld has fallen and you are out of this game."
            ))
            return

        self.stdout.write(
            self.style.SUCCESS(
                "Connected: game=%s year=%s player=%s (%s)"
                % (game.short_id, game.year, player.name, player.short_id)
            )
        )
        player.last_seen_year = game.year
        player.save(update_fields=["last_seen_year"])

        self._show_priority_messages(player, game)
        one_shot_command = (options.get("one_shot_command") or "").strip()
        if one_shot_command:
            self._execute_cli_command(one_shot_command, player, game)
            self.stdout.write("Disconnected.")
            return

        self.stdout.write("Type /help for available commands.")
        self._load_readline_history()

        while True:
            try:
                raw = input("play> ").strip()
            except (KeyboardInterrupt, EOFError):
                self.stdout.write("")
                break

            if not raw:
                continue

            if raw in ("/quit", "/exit"):
                break
            if raw == "/done":
                self._handle_done_command(player, game)
                break
            if readline is not None:
                readline.add_history(raw)
            self._execute_cli_command(raw, player, game)

        self._save_readline_history()
        self.stdout.write("Disconnected.")

    def _load_readline_history(self):
        if readline is None:
            return
        try:
            readline.read_history_file(self.HISTORY_PATH)
        except Exception:
            pass

    def _save_readline_history(self):
        if readline is None:
            return
        try:
            readline.set_history_length(int(self.HISTORY_LENGTH))
            readline.write_history_file(self.HISTORY_PATH)
        except Exception:
            pass

    def _execute_cli_command(self, raw, player, game):
        if self._handle_help_request(raw):
            return
        if raw == "/done":
            self._handle_done_command(player, game)
            return
        if raw == "/colonies":
            self._print_yaml(self._colonies_summary(player))
            return
        if raw.startswith("/fleets"):
            self._handle_fleets_command(raw, player)
            return
        if raw == "/stars":
            self._print_yaml(self._stars_summary(game, player))
            return
        if raw == "/status":
            self._print_yaml(self._status_summary(player, game))
            return
        if raw == "/reports":
            self._print_yaml(self._reports_summary(player))
            return
        if raw == "/anomalies":
            self._print_yaml(self._anomalies_summary(player))
            return
        if raw == "/salvage":
            self._print_yaml(self._salvage_summary(player))
            return
        if raw.startswith("/rename"):
            self._handle_rename_command(raw, player)
            return
        if raw.startswith("/notes"):
            self._handle_notes_command(raw, player)
            return
        if raw.startswith("/orders"):
            self._handle_orders_command(raw, player)
            return
        if raw.startswith("/research"):
            self._handle_research_command(raw, player)
            return
        if raw.startswith("/detail"):
            self._handle_detail_command(raw, player)
            return
        if raw.startswith("/messages"):
            self._handle_messages_command(raw, player, game)
            return
        self.stdout.write("Unknown command. Type /help.")

    def _handle_done_command(self, player, game):
        if game.turn_scheme != "QUORUM":
            self.stdout.write(
                "Turn-in skipped: game turn scheme is %s." % game.turn_scheme
            )
            return
        if game.is_generating:
            self.stdout.write("Turn generation is already in progress.")
            return

        if not player.turned_in:
            player.turned_in = True
            player.save(update_fields=["turned_in"])
        self.stdout.write("Player marked ready for turn generation.")

        turn = GameTurn(game)
        if turn.check_quorum():
            self.stdout.write("Quorum met. Generating turn...")
            turn.generate_turn()

    def _get_game(self, short_id):
        game = Game.objects.filter(short_id=short_id).first()
        if game is None:
            raise CommandError("Game not found: %s" % short_id)
        return game

    def _authenticate_user(self, username):
        if not username:
            username = input("Username: ").strip()
        if not username:
            raise CommandError("Username is required.")
        password = getpass.getpass("Password: ")
        user = authenticate(username=username, password=password)
        if user is None:
            raise CommandError("Authentication failed.")
        return user

    def _resolve_player(self, game, account, user, player_selector,
                        account_selector, no_auth):
        qs = Player.objects.filter(game=game).select_related(
            "account", "account__django_user"
        )
        player = None

        if player_selector:
            player = qs.filter(
                Q(short_id=player_selector) | Q(name=player_selector)
            ).first()
            if player is None:
                raise CommandError("Player not found: %s" % player_selector)

        if account_selector:
            target_account = Account.objects.filter(
                Q(alias=account_selector) |
                Q(django_user__username=account_selector)
            ).first()
            if target_account is None:
                raise CommandError("Account not found: %s" % account_selector)
            account_player = qs.filter(account=target_account).first()
            if account_player is None:
                raise CommandError(
                    "Account %s has no player in game %s"
                    % (account_selector, game.short_id)
                )
            if player and player.id != account_player.id:
                raise CommandError("Conflicting --player and --account selectors.")
            player = account_player

        if player is None and account is not None:
            player = qs.filter(account=account).first()

        if player is None:
            players = list(qs.order_by("name"))
            if not players:
                raise CommandError("Game has no players.")
            self.stdout.write("Select player:")
            for idx, p in enumerate(players, 1):
                alias = p.account.alias if p.account_id else "no-account"
                self.stdout.write(
                    "  %d. %s (%s) [%s]" % (idx, p.name, p.short_id, alias)
                )
            choice = input("Player #> ").strip()
            try:
                index = int(choice)
            except ValueError:
                raise CommandError("Invalid player selection.")
            if index < 1 or index > len(players):
                raise CommandError("Invalid player selection.")
            player = players[index - 1]

        if not no_auth and user is not None and not user.is_staff:
            if player.account_id != account.pk:
                raise CommandError(
                    "Authenticated user cannot play as another account's player."
                )

        return player

    def _show_priority_messages(self, player, game):
        qs = self._messages_base_queryset(player).filter(priority=True)
        msgs = list(qs[:20])
        if not msgs:
            return
        self.stdout.write(self.style.WARNING("Priority messages (year %s):" % game.year))
        payload = {}
        for msg in msgs:
            payload[msg.short_id] = {
                "year": msg.year,
                "category": msg.category,
                "message": self._format_message_text_for_cli(msg.message),
            }
        self._print_yaml({"priority_messages": payload})

    def _handle_help_request(self, raw):
        try:
            parts = shlex.split(raw)
        except ValueError:
            return False
        if not parts:
            return False

        command = self._normalize_help_token(parts[0])
        if command == "help":
            if len(parts) > 3:
                self.stdout.write("Usage: /help [command [action]]")
                return True
            topic = self._normalize_help_token(parts[1]) if len(parts) >= 2 else None
            action = self._normalize_help_token(parts[2]) if len(parts) >= 3 else None
            self._print_help(topic, action)
            return True

        if len(parts) == 2 and parts[1].strip().lower() == "help":
            self._print_help(command)
            return True

        if len(parts) == 3 and parts[2].strip().lower() == "help":
            action = self._normalize_help_token(parts[1])
            if self._command_has_help_action(command, action):
                self._print_help(command, action)
                return True

        return False

    def _normalize_help_token(self, token):
        return str(token or "").strip().lower().lstrip("/")

    def _command_has_help_action(self, command, action):
        topic = self._help_topics().get(command) or {}
        return action in (topic.get("actions") or {})

    def _help_topics(self):
        return {
            "help": {
                "summary": "/help                    Show general or filtered help.",
                "lines": [
                    "/help",
                    "Usage: /help [command [action]]",
                    "Also supported: /<command> help and /<command> <action> help.",
                ],
            },
            "colonies": {
                "summary": "/colonies                YAML summary of your colonies.",
                "lines": [
                    "/colonies",
                    "Shows your colonies with current visible data.",
                ],
            },
            "fleets": {
                "summary": "/fleets [own|other|all]  YAML summary of fleet intelligence.",
                "lines": [
                    "/fleets",
                    "Usage: /fleets [own|other|all]",
                    "Default /fleets is the same as /fleets own.",
                    "Shows your fleets in detail, or known other/all fleets through the report/scanner system.",
                ],
                "actions": {
                    "own": [
                        "/fleets own",
                        "Usage: /fleets [own]",
                        "Shows your own fleets with full current management detail.",
                    ],
                    "other": [
                        "/fleets other",
                        "Usage: /fleets other",
                        "Shows only known non-owned fleets, gated by current visibility or cached reports.",
                    ],
                    "all": [
                        "/fleets all",
                        "Usage: /fleets all",
                        "Shows both your fleets and known non-owned fleets.",
                    ],
                },
            },
            "stars": {
                "summary": "/stars                   YAML summary of stars and known status.",
                "lines": [
                    "/stars",
                    "Shows stars with your current knowledge status.",
                ],
            },
            "status": {
                "summary": "/status                  YAML turn/year status for this game.",
                "lines": [
                    "/status",
                    "Shows current year, turn scheme, quorum/turn-in status, and next turn timing when available.",
                ],
            },
            "reports": {
                "summary": "/reports                 YAML summary of known objects and report years.",
                "lines": [
                    "/reports",
                    "Lists your known objects with name, report year, owner, location, class, and subclass/fleet count.",
                ],
            },
            "anomalies": {
                "summary": "/anomalies               YAML summary of all visible anomalies.",
                "lines": [
                    "/anomalies",
                    "Lists all map-visible anomalies. Hidden detail fields remain obscured.",
                ],
            },
            "salvage": {
                "summary": "/salvage                 YAML summary of known salvage.",
                "lines": [
                    "/salvage",
                    "Lists salvage you currently know about.",
                ],
            },
            "rename": {
                "summary": "/rename <id> \"Name\"      Rename one of your fleets or colonies.",
                "lines": [
                    "/rename",
                    'Usage: /rename <fleet_or_colony_id_or_"Exact Name"> "New Name"',
                    "Renames one of your own fleets or colonies.",
                    "Selector may be a short_id or a quoted exact current name.",
                ],
            },
            "notes": {
                "summary": "/notes                   YAML list of your saved notes.",
                "lines": [
                    "/notes",
                    "Usage: /notes [add [id] text|remove <id>]",
                    "Lists your saved player notes, or routes to note subcommands.",
                ],
                "actions": {
                    "add": [
                        "/notes add",
                        "Usage: /notes add [id] text",
                        "Adds a note. If id is omitted, the next numeric id is used.",
                    ],
                    "remove": [
                        "/notes remove",
                        "Usage: /notes remove <id>",
                        "Removes one of your saved notes.",
                    ],
                },
            },
            "orders": {
                "summary": "/orders <id>             List orders for your fleet/star.",
                "lines": [
                    "/orders",
                    "Usage: /orders <fleet_or_star_short_id> [list|clear|add ...]",
                    "Lists, clears, or adds orders for one of your fleets or colonies.",
                    "Use /help orders add or /orders add help for add syntax guidance.",
                ],
                "actions": {
                    "list": [
                        "/orders list",
                        "Usage: /orders <fleet_or_star_short_id> [list]",
                        "Lists the current orders for the selected fleet or colony.",
                    ],
                    "clear": [
                        "/orders clear",
                        "Usage: /orders <fleet_or_star_short_id> clear",
                        "Clears all orders for the selected fleet or colony.",
                    ],
                    "add": [
                        "/orders add",
                        "Usage: /orders <fleet_id> add",
                        "Usage: /orders <fleet_id> add <ORDER_TYPE> <params...>",
                        "Usage: /orders <star_id> add",
                        "Usage: /orders <star_id> add <TYPE_OR_ALIAS> [quantity] [repeat]",
                        "Run /orders <id> add to print the target-specific YAML syntax block.",
                    ],
                },
            },
            "research": {
                "summary": "/research                Budget + category levels/allocations.",
                "lines": [
                    "/research",
                    "Usage: /research [CODE [PERCENT]]",
                    "Without arguments: show budget and category overview.",
                    "With CODE: show category detail.",
                    "With CODE and PERCENT: set allocation and rebalance.",
                ],
            },
            "detail": {
                "summary": "/detail <object_id>      YAML detail panel data as visible to this player.",
                "lines": [
                    "/detail",
                    'Usage: /detail <object_short_id_or_"Exact Name">',
                    "Shows detail panel data for one object visible to this player.",
                    "Quote exact names to search by name.",
                ],
            },
            "messages": {
                "summary": "/messages [filters...]   YAML messages list (same defaults as game panel).",
                "lines": [
                    "/messages",
                    "Usage: /messages [year=YYYY] [since=YYYY] [category=CAT] [priority=1|0] [limit=N] [contains=text]",
                    "Shows messages with the same defaults as the main game panel.",
                ],
            },
            "done": {
                "summary": "/done                    Turn in and exit in quorum games.",
                "lines": [
                    "/done",
                    "Marks you ready for turn generation and exits the CLI.",
                ],
            },
            "quit": {
                "summary": "/quit or /exit           Exit CLI.",
                "lines": [
                    "/quit or /exit",
                    "Exit the Play CLI.",
                ],
            },
            "exit": {
                "summary": "/quit or /exit           Exit CLI.",
                "lines": [
                    "/quit or /exit",
                    "Exit the Play CLI.",
                ],
            },
        }

    def _print_help(self, command=None, action=None):
        topics = self._help_topics()
        if not command:
            lines = [
                topic["summary"]
                for name, topic in topics.items()
                if name in (
                    "help", "colonies", "fleets", "stars", "status", "reports",
                    "anomalies", "salvage", "rename", "notes", "orders",
                    "research", "detail", "messages", "done", "quit",
                )
            ]
            lines.append("Type /help <command> or /<command> help for details.")
            lines.append("Type /help <command> <action> or /<command> <action> help for subcommands.")
            self.stdout.write("\n".join(lines))
            return

        topic = topics.get(command)
        if topic is None:
            self.stdout.write("Unknown help topic: %s" % command)
            return

        if action:
            action_lines = (topic.get("actions") or {}).get(action)
            if action_lines is None:
                self.stdout.write("Unknown /%s help topic: %s" % (command, action))
                return
            self.stdout.write("\n".join(action_lines))
            return

        self.stdout.write("\n".join(topic["lines"]))

    def _colonies_summary(self, player):
        stars = Star.objects.filter(
            game=player.game, player=player
        ).order_by("name", "x", "y")
        data = {}
        for star in stars:
            resources = {
                "ironium_kt": star.ironium_inventory,
                "boranium_kt": star.boranium_inventory,
                "germanium_kt": star.germanium_inventory,
            }
            for key in SECRET_RESOURCE_KEYS:
                amount = int(getattr(star, f"{key}_inventory", 0) or 0)
                if amount > 0:
                    resources[f"{key}_kt"] = amount
            data[star.short_id] = {
                "name": star.name,
                "position": "(%s, %s)" % (star.x, star.y),
                "colonists_kt": star.colonists,
                "resources": resources,
                "infrastructure": {
                    "mines": star.mines,
                    "factories": star.factories,
                    "labs": star.labs,
                    "defenses": star.defenses,
                    "shipyards": star.shipyards,
                },
            }
        return data

    def _stars_summary(self, game, player):
        explored_star_ids = set(
            Report.objects.filter(
                game=game, player=player, target_type="star"
            ).values_list("target_id", flat=True)
        )
        stars = Star.objects.filter(game=game).order_by("x", "y", "name")
        data = {}
        for star in stars:
            explored = star.player_id == player.id or star.id in explored_star_ids
            owner_player = None
            if not explored:
                status = "unknown"
                habitable = None
            elif star.player_id == player.id:
                status = "colonised_owned"
                habitable = calculate_habitability_factor(player, star) >= 0
            elif star.player_id:
                status = "colonised_other"
                habitable = calculate_habitability_factor(player, star) >= 0
                owner_player = star.player.name if star.player else None
            else:
                status = "known_uncolonised"
                habitable = calculate_habitability_factor(player, star) >= 0

            if habitable is True:
                status = "%s, habitable" % status
            data[star.short_id] = {
                "name": star.name,
                "position": "(%s, %s)" % (star.x, star.y),
                "status": status,
                "explored": bool(explored),
                "owner_player": owner_player,
            }
        return data

    def _handle_fleets_command(self, raw, player):
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            self.stdout.write("Invalid command syntax: %s" % exc)
            return
        if len(parts) == 1:
            scope = "own"
        elif len(parts) == 2:
            scope = parts[1].strip().lower()
        else:
            self.stdout.write("Usage: /fleets [own|other|all]")
            return
        if scope not in ("own", "other", "all"):
            self.stdout.write("Usage: /fleets [own|other|all]")
            return
        self._print_yaml(self._fleets_summary(player, scope))

    def _fleets_summary(self, player, scope="own"):
        if scope == "own":
            return self._own_fleets_summary(player)
        return self._known_fleets_summary(player, scope)

    def _own_fleets_summary(self, player):
        fleets = player.fleets.order_by("name", "x", "y")
        data = {}
        for fleet in fleets:
            cargo = {
                "ironium_kt": fleet.ironium_inventory,
                "boranium_kt": fleet.boranium_inventory,
                "germanium_kt": fleet.germanium_inventory,
                "colonists_kt": fleet.colonists,
            }
            for key in SECRET_RESOURCE_KEYS:
                amount = int(getattr(fleet, f"{key}_inventory", 0) or 0)
                if amount > 0:
                    cargo[f"{key}_kt"] = amount
            data[fleet.short_id] = {
                "name": fleet.name,
                "owner": fleet.player.name if fleet.player_id else None,
                "is_owned": True,
                "visibility": "current",
                "position": "(%s, %s)" % (fleet.x, fleet.y),
                "ship_count": fleet.ship_count,
                "number_of_orders": fleet.orders.count(),
                "integrity_pct": fleet.integrity,
                "fuel_mg": float(fleet.fuel),
                "cargo_capacity_kt": fleet.cargo_capacity,
                "cargo": cargo,
                "max_safe_warp": fleet.max_safe_warp,
            }
        return data

    def _known_fleets_summary(self, player, scope):
        fleets = Fleet.objects.filter(game=player.game).order_by("x", "y", "name", "id")
        data = {}
        for fleet in fleets:
            detail = DetailBuilder(
                player.game, selected=fleet.short_id, player=player
            ).build_detail()
            if not detail or detail.get("unexplored"):
                continue
            is_owned = bool(fleet.player_id == player.id)
            if scope == "other" and is_owned:
                continue

            entry = self._build_map_object_summary_entry(detail)
            entry["owner"] = self._report_owner_name(fleet, detail)
            entry["is_owned"] = is_owned
            ship_count = self._fleet_ship_count_from_detail(fleet, detail)
            if ship_count is not None:
                entry["ship_count"] = ship_count
            data[fleet.short_id] = entry
        return data

    def _fleet_ship_count_from_detail(self, fleet, detail):
        if detail.get("is_current"):
            return int(getattr(fleet, "ship_count", 0) or 0)
        fleet_cargo = detail.get("fleet_cargo") or {}
        ship_count = fleet_cargo.get("ship_count")
        if ship_count is None:
            return None
        try:
            return int(ship_count)
        except (TypeError, ValueError):
            return None

    def _anomalies_summary(self, player):
        anomalies = Anomaly.objects.filter(game=player.game).order_by("x", "y", "name", "id")
        data = {}
        for anomaly in anomalies:
            detail = DetailBuilder(
                player.game, selected=anomaly.short_id, player=player
            ).build_detail()
            if not detail:
                continue
            entry = self._build_map_object_summary_entry(detail)
            if detail.get("anomaly_type"):
                entry["anomaly_type"] = detail.get("anomaly_type")
            if detail.get("stability") is not None:
                entry["stability_pct"] = detail.get("stability")
            if detail.get("heading") is not None:
                entry["heading"] = round(float(detail.get("heading")), 1)
            data[anomaly.short_id] = entry
        return data

    def _status_summary(self, player, game):
        active_players = game.players.filter(defeated=False).count()
        summary = {
            "year": game.year,
            "turn_scheme": game.turn_scheme,
            "turn_scheme_label": game.get_turn_scheme_short_display(),
            "is_generating": bool(game.is_generating),
            "turned_in": bool(player.turned_in),
            "active_players": active_players,
        }
        if game.turn_scheme == "QUORUM":
            ready_players = game.players.filter(defeated=False, turned_in=True).count()
            summary["ready_players"] = ready_players
        if game.next_generation:
            summary["next_generation"] = timezone.localtime(game.next_generation).isoformat()
            summary["time_to_next_turn"] = self._format_time_to_next_turn(game.next_generation)
        if game.turn_scheme == "OWNER":
            summary["owner_can_generate"] = bool(player.account_id and player.account_id == game.owner_id)
        return summary

    def _reports_summary(self, player):
        objects = []
        objects.extend(Star.objects.filter(game=player.game).order_by("x", "y", "name", "id"))
        objects.extend(Fleet.objects.filter(game=player.game).order_by("x", "y", "name", "id"))
        objects.extend(Salvage.objects.filter(game=player.game).order_by("x", "y", "id"))
        objects.extend(Anomaly.objects.filter(game=player.game).order_by("x", "y", "name", "id"))

        data = {}
        for obj in objects:
            detail = DetailBuilder(player.game, selected=obj.short_id, player=player).build_detail()
            if not detail or detail.get("unexplored"):
                continue
            report_year = detail.get("report_year")
            if report_year is None and detail.get("is_current"):
                report_year = player.game.year
            owner = self._report_owner_name(obj, detail)
            entry = {
                "name": detail.get("name") or getattr(obj, "name", None),
                "report_year": report_year,
                "location": "(%s, %s)" % (detail.get("x"), detail.get("y")),
                "object_class": self._report_object_class(detail),
            }
            if owner is not None:
                entry["owner"] = owner
            subclass = self._report_object_subclass(obj, detail)
            if subclass:
                entry["subclass"] = subclass
            fleet_count = self._report_fleet_count(obj, detail)
            if fleet_count is not None:
                entry["fleet_count"] = fleet_count
            data[obj.short_id] = entry
        return data

    def _salvage_summary(self, player):
        salvages = Salvage.objects.filter(game=player.game).order_by("x", "y", "id")
        data = {}
        for salvage in salvages:
            detail = DetailBuilder(
                player.game, selected=salvage.short_id, player=player
            ).build_detail()
            if not detail:
                continue
            if detail.get("unexplored") and not getattr(player.game, "no_scanners", False):
                continue
            entry = self._build_map_object_summary_entry(detail)
            salvage_inventory = detail.get("salvage_inventory") or {}
            total = salvage_inventory.get("total")
            if total is not None:
                entry["total_minerals_kt"] = total
            data[salvage.short_id] = entry
        return data

    def _handle_rename_command(self, raw, player):
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            self.stdout.write("Invalid command syntax: %s" % exc)
            return
        if len(parts) < 3:
            self.stdout.write('Usage: /rename <fleet_or_colony_id_or_"Exact Name"> "New Name"')
            return
        selector = parts[1]
        new_name = " ".join(parts[2:]).strip()
        if not new_name:
            self.stdout.write("New name is required.")
            return
        if len(new_name) > 30:
            self.stdout.write("Name must be 30 characters or less.")
            return
        try:
            obj = self._resolve_owned_rename_target(player, selector)
        except CommandError as exc:
            self.stdout.write(str(exc))
            return
        if obj is None:
            self.stdout.write("Rename target not found for this player: %s" % selector)
            return
        old_name = obj.name
        obj.name = new_name
        obj.save(update_fields=["name"])
        self.stdout.write(
            'Renamed %s <%s> from "%s" to "%s".'
            % (obj.__class__.__name__, obj.short_id, old_name, new_name)
        )

    def _handle_notes_command(self, raw, player):
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            self.stdout.write("Invalid command syntax: %s" % exc)
            return
        if len(parts) == 1:
            self._print_yaml(self._notes_summary(player))
            return
        action = parts[1].strip().lower()
        if action == "add":
            self._handle_notes_add(player, parts[2:])
            return
        if action == "remove":
            self._handle_notes_remove(player, parts[2:])
            return
        self.stdout.write("Usage: /notes [add [id] text|remove <id>]")

    def _notes_summary(self, player):
        payload = {}
        for note in player.notes.order_by("note_id"):
            payload[int(note.note_id)] = note.text
        return payload

    def _handle_notes_add(self, player, args):
        if not args:
            self.stdout.write("Usage: /notes add [id] text")
            return
        note_id = None
        text_parts = list(args)
        try:
            note_id = int(args[0])
            text_parts = args[1:]
        except (TypeError, ValueError):
            note_id = None
        text = " ".join(text_parts).strip()
        if not text:
            self.stdout.write("Note text is required.")
            return
        if note_id is None:
            note_id = self._next_note_id(player)
        if note_id <= 0:
            self.stdout.write("Note id must be a positive integer.")
            return
        if player.notes.filter(note_id=note_id).exists():
            self.stdout.write("Note id already exists: %s" % note_id)
            return
        PlayerNote.objects.create(player=player, note_id=note_id, text=text)
        self.stdout.write("Saved note %s." % note_id)

    def _handle_notes_remove(self, player, args):
        if len(args) != 1:
            self.stdout.write("Usage: /notes remove <id>")
            return
        try:
            note_id = int(args[0])
        except ValueError:
            self.stdout.write("Note id must be a positive integer.")
            return
        note = player.notes.filter(note_id=note_id).first()
        if note is None:
            self.stdout.write("Note not found: %s" % note_id)
            return
        note.delete()
        self.stdout.write("Removed note %s." % note_id)

    def _next_note_id(self, player):
        current_max = player.notes.aggregate(max_note_id=Max("note_id")).get("max_note_id")
        return int(current_max or 0) + 1

    def _build_map_object_summary_entry(self, detail):
        if detail.get("unexplored"):
            visibility = "visible"
        else:
            visibility = "current" if detail.get("is_current") else "report"
        entry = {
            "name": detail.get("name"),
            "position": "(%s, %s)" % (detail.get("x"), detail.get("y")),
            "visibility": visibility,
        }
        if detail.get("report_year") is not None:
            entry["report_year"] = detail.get("report_year")
        if detail.get("report_tier"):
            entry["report_tier"] = detail.get("report_tier")
        return entry

    def _format_time_to_next_turn(self, next_generation):
        delta = timezone.localtime(next_generation) - timezone.localtime(timezone.now())
        if delta.total_seconds() <= 0:
            return "due"
        return self._format_duration(delta)

    def _format_duration(self, delta):
        total_seconds = int(delta.total_seconds())
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _seconds = divmod(rem, 60)
        parts = []
        if days:
            parts.append("%dd" % days)
        if hours or days:
            parts.append("%dh" % hours)
        parts.append("%dm" % minutes)
        return " ".join(parts)

    def _report_owner_name(self, obj, detail):
        owner = detail.get("player")
        if owner and detail.get("is_current") and getattr(obj, "player", None) is not None:
            return obj.player.name
        return owner

    def _report_object_class(self, detail):
        if detail.get("is_star"):
            return "star"
        if detail.get("is_fleet"):
            return "fleet"
        if detail.get("is_salvage"):
            return "salvage"
        if detail.get("is_anomaly"):
            return "anomaly"
        return "object"

    def _report_object_subclass(self, obj, detail):
        if detail.get("is_salvage"):
            return obj.get_salvage_type_display()
        if detail.get("is_anomaly") and detail.get("anomaly_type"):
            return obj.get_anomaly_type_display()
        return None

    def _report_fleet_count(self, obj, detail):
        if detail.get("is_fleet"):
            return int(getattr(obj, "ship_count", 0) or 0)
        return None

    def _handle_orders_command(self, raw, player):
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            self.stdout.write("Invalid command syntax: %s" % exc)
            return
        if len(parts) < 2:
            self.stdout.write("Usage: /orders <fleet_or_star_short_id> [clear|add ...]")
            return
        object_short_id = parts[1].strip()
        target, target_kind = self._resolve_orders_target(player, object_short_id)
        if target is None:
            self.stdout.write(
                "Orders target not found for this player: %s" % object_short_id
            )
            return
        if len(parts) == 2:
            self._print_orders_list(target, target_kind)
            return

        action = parts[2].strip().lower()
        if action == "list":
            self._print_orders_list(target, target_kind)
            return
        if action == "clear":
            if player.turned_in:
                self.stdout.write("Orders are locked after turn-in.")
                return
            self._clear_orders(target, target_kind)
            self._print_orders_list(target, target_kind)
            return
        if action == "add":
            if player.turned_in:
                self.stdout.write("Orders are locked after turn-in.")
                return
            if len(parts) == 3:
                self._print_yaml(self._orders_add_help(target_kind))
                return
            self._add_order(target, target_kind, parts[3:])
            self._print_orders_list(target, target_kind)
            return

        self.stdout.write(
            "Unknown /orders action: %s (expected list|clear|add)" % parts[2]
        )

    def _resolve_orders_target(self, player, short_id):
        fleet = Fleet.objects.filter(
            game=player.game,
            player=player,
            short_id=short_id,
        ).first()
        if fleet is not None:
            return fleet, "fleet"
        star = Star.objects.filter(
            game=player.game,
            player=player,
            short_id=short_id,
        ).first()
        if star is not None:
            return star, "star"
        return None, None

    def _print_orders_list(self, target, target_kind):
        if target_kind == "fleet":
            self._print_yaml({target.short_id: self._fleet_orders_summary(target)})
            return
        self._print_yaml({target.short_id: self._star_orders_summary(target)})

    def _star_orders_summary(self, star):
        payload = {}
        orders = star.production_orders.order_by("position", "id")
        for order in orders:
            payload[order.short_id] = {
                "position": order.position,
                "type": order.order_type,
                "display": order.get_order_type_display(),
                "quantity": order.quantity,
                "completed": order.completed,
                "repeat": bool(order.repeat),
                "cost_per_item": PRODUCTION_COSTS.get(order.order_type, {}),
            }
        return payload

    def _clear_orders(self, target, target_kind):
        if target_kind == "fleet":
            target.orders.all().delete()
            return
        target.production_orders.all().delete()

    def _orders_add_help(self, target_kind):
        if target_kind == "fleet":
            return {
                "fleet_order_types": {
                    "MOVE": {
                        "syntax": "/orders <fleet_id> add MOVE <(x,y)|target_id> [warp=N|wormhole] [repeat]",
                    },
                    "INTERCEPT": {
                        "syntax": "/orders <fleet_id> add INTERCEPT <fleet_id> [warp=N] [repeat]",
                    },
                    "TRANSFER": {
                        "syntax": (
                            "/orders <fleet_id> add TRANSFER <target_id|x,y> "
                            "<load|unload|unload_all> "
                            "[ironium=N] [boranium=N] [germanium=N] "
                            "[resource_x=N] [resource_y=N] [resource_z=N] "
                            "[colonists=N] [repeat]"
                        ),
                    },
                    "COLONISE": {
                        "syntax": "/orders <fleet_id> add COLONISE <star_id>",
                    },
                    "BOMB": {
                        "syntax": "/orders <fleet_id> add BOMB <star_id> [bomb_until=colonists_zero|defenses_zero|once] [repeat]",
                    },
                    "REMOTEMINE": {
                        "syntax": "/orders <fleet_id> add REMOTEMINE <star_id> [mine_until_full=1|0] [focus=ironium,boranium,...] [repeat]",
                    },
                    "MERGE": {
                        "syntax": "/orders <fleet_id> add MERGE <fleet_id>",
                    },
                    "SCUTTLE": {"syntax": "/orders <fleet_id> add SCUTTLE"},
                    "PATROL": {
                        "syntax": (
                            "/orders <fleet_id> add PATROL <(x,y)|target_id> "
                            "[radius=N] [intercept_speed=N] [repeat]"
                        ),
                    },
                }
            }
        return {
            "star_production_order_types": {
                "BUILD_MINE": {"aliases": ["MINE"], "params": ["quantity", "repeat"]},
                "BUILD_FACTORY": {"aliases": ["FACTORY"], "params": ["quantity", "repeat"]},
                "BUILD_LAB": {"aliases": ["LAB"], "params": ["quantity", "repeat"]},
                "BUILD_DEFENSE": {"aliases": ["DEFENSE"], "params": ["quantity", "repeat"]},
                "BUILD_SHIPYARD": {"aliases": ["SHIPYARD"], "params": ["quantity", "repeat"]},
                "BUILD_FLEET": {"aliases": ["FLEET"], "params": ["quantity", "repeat"]},
                "TERRAFORM_GRAVITY": {"aliases": ["TERRAFORM_GRAVITY"], "params": ["quantity", "repeat"]},
                "TERRAFORM_TEMPERATURE": {"aliases": ["TERRAFORM_TEMPERATURE"], "params": ["quantity", "repeat"]},
                "TERRAFORM_RADIATION": {"aliases": ["TERRAFORM_RADIATION"], "params": ["quantity", "repeat"]},
                "syntax": "/orders <star_id> add <type_or_alias> [quantity] [repeat]",
            }
        }

    def _add_order(self, target, target_kind, args):
        try:
            if target_kind == "fleet":
                self._add_fleet_order(target, args)
            else:
                self._add_star_order(target, args)
        except CommandError as exc:
            self.stdout.write(str(exc))

    def _add_star_order(self, star, args):
        if not args:
            raise CommandError("Usage: /orders <star_id> add <type> [quantity] [repeat]")

        order_token = args[0].strip().upper()
        aliases = {
            "MINE": "BUILD_MINE",
            "FACTORY": "BUILD_FACTORY",
            "LAB": "BUILD_LAB",
            "DEFENSE": "BUILD_DEFENSE",
            "SHIPYARD": "BUILD_SHIPYARD",
            "FLEET": "BUILD_FLEET",
        }
        order_type = aliases.get(order_token, order_token)
        valid_types = set(v for v, _ in ProductionOrder.ORDER_TYPES)
        if order_type not in valid_types:
            raise CommandError("Unknown production order type: %s" % order_token)
        if order_type.startswith("TERRAFORM_"):
            allowed = {
                entry["value"]
                for entry in get_player_available_production_orders(star.player, star)
            }
            if order_type not in allowed:
                raise CommandError("Terraforming requires a terraforming technology.")

        quantity = 1
        repeat = False
        for token in args[1:]:
            lower = token.strip().lower()
            if lower == "repeat":
                repeat = True
                continue
            try:
                quantity = max(1, int(token))
            except ValueError:
                raise CommandError("Invalid production quantity token: %s" % token)

        max_pos = star.production_orders.aggregate(max_pos=Max("position"))["max_pos"] or 0
        ProductionOrder.objects.create(
            game=star.game,
            star=star,
            order_type=order_type,
            position=max_pos + 1,
            quantity=quantity,
            repeat=repeat,
        )

    def _add_fleet_order(self, fleet, args):
        if not args:
            raise CommandError(
                "Usage: /orders <fleet_id> add <type> <params...> [repeat]"
            )
        order_type = args[0].strip().upper()
        valid_types = set(v for v, _ in FleetOrders.ORDER_TYPE_CHOICES)
        if order_type not in valid_types:
            raise CommandError("Unknown fleet order type: %s" % order_type)

        extras = self._parse_order_extras(args[1:])
        repeat = bool(extras["repeat"])

        order = FleetOrders(
            game=fleet.game,
            fleet=fleet,
            order_type=order_type,
            repeat=repeat,
        )

        if order_type in ("MOVE", "INTERCEPT"):
            if not extras["positionals"]:
                raise CommandError("MOVE/INTERCEPT requires a target.")
            target_token = extras["positionals"][0]
            target_obj, x, y, kind = self._resolve_target_token(fleet.player, fleet.game, target_token)
            warp = extras["kwargs"].get("warp", extras["kwargs"].get("warpfactor"))
            order.warpfactor = self._parse_warp_value(
                warp, fleet.max_safe_warp, fleet, allow_wormhole=(order_type == "MOVE")
            )
            self._assign_fleet_order_target(order, target_obj, x, y, kind)
            if order_type == "INTERCEPT":
                if kind != "fleet":
                    raise CommandError("INTERCEPT target must be a fleet short_id.")
                order.target_fleet = target_obj

        elif order_type == "TRANSFER":
            if len(extras["positionals"]) < 2:
                raise CommandError(
                    "TRANSFER requires: <target> <load|unload|unload_all> [resources]"
                )
            target_token = extras["positionals"][0]
            transfer_token = extras["positionals"][1].strip().upper()
            transfer_aliases = {"LOAD": "LOAD", "UNLOAD": "UNLOAD", "UNLOAD_ALL": "UNLOAD_ALL"}
            if transfer_token not in transfer_aliases:
                raise CommandError("Invalid transfer type: %s" % extras["positionals"][1])
            order.transfer_type = transfer_aliases[transfer_token]
            target_obj, x, y, kind = self._resolve_target_token(fleet.player, fleet.game, target_token)
            self._assign_fleet_order_target(order, target_obj, x, y, kind)
            if kind == "fleet" and target_obj.player_id != fleet.player_id:
                raise CommandError("TRANSFER to fleet requires one of your own fleets.")

            order.transfer_ironium = self._parse_nonnegative_int(extras["kwargs"].get("ironium", 0), "ironium")
            order.transfer_boranium = self._parse_nonnegative_int(extras["kwargs"].get("boranium", 0), "boranium")
            order.transfer_germanium = self._parse_nonnegative_int(extras["kwargs"].get("germanium", 0), "germanium")
            order.transfer_resource_x = self._parse_nonnegative_int(
                extras["kwargs"].get("resource_x", 0), "resource_x"
            )
            order.transfer_resource_y = self._parse_nonnegative_int(
                extras["kwargs"].get("resource_y", 0), "resource_y"
            )
            order.transfer_resource_z = self._parse_nonnegative_int(
                extras["kwargs"].get("resource_z", 0), "resource_z"
            )
            order.transfer_colonists = self._parse_nonnegative_int(extras["kwargs"].get("colonists", 0), "colonists")
            self._apply_transfer_defaults_if_empty(order, target_obj, kind)

        elif order_type == "COLONISE":
            if not extras["positionals"]:
                raise CommandError("COLONISE requires a star short_id target.")
            target_obj, _, _, kind = self._resolve_target_token(fleet.player, fleet.game, extras["positionals"][0])
            if kind != "star":
                raise CommandError("COLONISE target must be a star short_id.")
            order.repeat = False
            order.target_star = target_obj

        elif order_type == "BOMB":
            if not fleet.has_bombs:
                raise CommandError("BOMB requires a fleet with bombs.")
            if not extras["positionals"]:
                raise CommandError("BOMB requires a star short_id target.")
            target_obj, _, _, kind = self._resolve_target_token(fleet.player, fleet.game, extras["positionals"][0])
            if kind != "star":
                raise CommandError("BOMB target must be a star short_id.")
            bomb_until = str(extras["kwargs"].get("bomb_until", "COLONISTS_ZERO")).strip().upper()
            if bomb_until == "CONTINUOUS":
                bomb_until = "ONCE"
            if bomb_until not in ("COLONISTS_ZERO", "DEFENSES_ZERO", "ONCE"):
                raise CommandError("BOMB bomb_until must be one of: colonists_zero, defenses_zero, once.")
            order.bomb_until = bomb_until
            order.target_star = target_obj

        elif order_type == "REMOTEMINE":
            if not fleet.has_miners:
                raise CommandError("REMOTEMINE requires a fleet with remote miners.")
            if not extras["positionals"]:
                raise CommandError("REMOTEMINE requires a star short_id target.")
            target_obj, _, _, kind = self._resolve_target_token(fleet.player, fleet.game, extras["positionals"][0])
            if kind != "star":
                raise CommandError("REMOTEMINE target must be a star short_id.")
            mine_until_full = str(extras["kwargs"].get("mine_until_full", "1")).strip().lower()
            order.mine_until_full = mine_until_full not in ("0", "false", "off", "no")
            order.target_star = target_obj
            focus_raw = extras["kwargs"].get("focus", extras["kwargs"].get("remotemine_focus", ""))
            focus_keys = self._parse_remotemine_focus_keys(focus_raw)
            if str(fleet.has_miners).strip().upper() == "LARGE" and focus_keys:
                allowed = set(known_resource_keys(fleet.player, target_obj))
                focus_keys = [key for key in focus_keys if key in allowed]
                order.remotemine_focus = ",".join(focus_keys)
            else:
                order.remotemine_focus = ""

        elif order_type == "MERGE":
            if not extras["positionals"]:
                raise CommandError("MERGE requires a target fleet short_id.")
            target_obj, _, _, kind = self._resolve_target_token(fleet.player, fleet.game, extras["positionals"][0])
            if kind != "fleet":
                raise CommandError("MERGE target must be a fleet short_id.")
            if target_obj.player_id != fleet.player_id:
                raise CommandError("MERGE target must be one of your own fleets.")
            order.repeat = False
            order.target_fleet = target_obj

        elif order_type == "SCUTTLE":
            order.repeat = False

        elif order_type == "PATROL":
            if not extras["positionals"]:
                raise CommandError("PATROL requires a target.")
            target_obj, x, y, kind = self._resolve_target_token(fleet.player, fleet.game, extras["positionals"][0])
            self._assign_fleet_order_target(order, target_obj, x, y, kind)
            radius = extras["kwargs"].get("radius", extras["kwargs"].get("patrol_radius"))
            intercept_speed = extras["kwargs"].get("intercept_speed")
            order.patrol_radius = self._parse_int_or_default(radius, 15, "radius")
            order.intercept_speed = self._parse_warp_value(
                intercept_speed, fleet.max_safe_warp, fleet, "intercept_speed", False
            )

        target_obj, target_x, target_y, target_kind = order.get_actual_target()
        if target_kind in ("star", "fleet", "salvage", "anomaly") and target_obj is not None:
            order.target_kind = "OBJECT"
            order.target_short_id = target_obj.short_id
        elif target_kind == "space":
            order.target_kind = "SPACE"
            order.target_short_id = None
            order.x = target_x
            order.y = target_y
        else:
            order.target_kind = None
            order.target_short_id = None

        order.save()

    def _parse_order_extras(self, tokens):
        positionals = []
        kwargs = {}
        repeat = False
        for token in tokens:
            lower = token.strip().lower()
            if lower == "repeat":
                repeat = True
                continue
            if "=" in token:
                key, value = token.split("=", 1)
                kwargs[key.strip().lower()] = value.strip()
                continue
            positionals.append(token.strip())
        return {"positionals": positionals, "kwargs": kwargs, "repeat": repeat}

    def _resolve_target_token(self, player, game, token):
        coords = self._parse_coords_token(token)
        if coords is not None:
            return None, coords[0], coords[1], "space"
        target_id = token.strip().lower()
        star = Star.objects.filter(game=game, short_id=target_id).first()
        if star is not None:
            return star, star.x, star.y, "star"
        fleet = Fleet.objects.filter(game=game, short_id=target_id).first()
        if fleet is not None and self._is_cli_object_discoverable(player, fleet):
            return fleet, fleet.x, fleet.y, "fleet"
        salvage = Salvage.objects.filter(game=game, short_id=target_id).first()
        if salvage is not None and (
            getattr(game, "no_scanners", False) or self._is_cli_object_discoverable(player, salvage)
        ):
            return salvage, salvage.x, salvage.y, "salvage"
        anomaly = Anomaly.objects.filter(game=game, short_id=target_id).first()
        if anomaly is not None:
            return anomaly, anomaly.x, anomaly.y, "anomaly"
        raise CommandError("Unknown target token: %s" % token)

    def _parse_coords_token(self, token):
        stripped = token.strip().replace(" ", "")
        if stripped.startswith("(") and stripped.endswith(")"):
            stripped = stripped[1:-1]
        if "," not in stripped:
            return None
        left, right = stripped.split(",", 1)
        if not left or not right:
            return None
        try:
            return int(left), int(right)
        except ValueError:
            return None

    def _assign_fleet_order_target(self, order, target_obj, x, y, kind):
        order.target_star = None
        order.target_fleet = None
        order.target_salvage = None
        order.target_short_id = None
        order.target_kind = None
        order.x = None
        order.y = None

        if kind == "star":
            order.target_star = target_obj
            order.target_short_id = target_obj.short_id
            order.target_kind = "OBJECT"
            order.x = target_obj.x
            order.y = target_obj.y
        elif kind == "fleet":
            order.target_fleet = target_obj
            order.target_short_id = target_obj.short_id
            order.target_kind = "OBJECT"
            order.x = target_obj.x
            order.y = target_obj.y
        elif kind == "salvage":
            order.target_salvage = target_obj
            order.target_short_id = target_obj.short_id
            order.target_kind = "OBJECT"
            order.x = target_obj.x
            order.y = target_obj.y
        elif kind == "anomaly":
            order.target_short_id = target_obj.short_id
            order.target_kind = "OBJECT"
            order.x = target_obj.x
            order.y = target_obj.y
        elif kind == "space":
            order.x = x
            order.y = y
            order.target_kind = "SPACE"
        else:
            raise CommandError("Invalid target kind: %s" % kind)

    def _parse_int_or_default(self, raw, default, label):
        if raw is None:
            return int(default)
        try:
            return int(raw)
        except ValueError:
            raise CommandError("Invalid %s value: %s" % (label, raw))

    def _parse_warp_value(self, raw, default, fleet, label="warp", allow_wormhole=True):
        if raw is None:
            value = int(default)
        else:
            token = str(raw).strip().lower()
            if token == "wormhole":
                value = 14
            else:
                try:
                    value = int(token)
                except ValueError:
                    raise CommandError("Invalid %s value: %s" % (label, raw))
        value = max(0, min(14, value))
        if value == 14 and not allow_wormhole:
            raise CommandError("%s=wormhole is only supported for MOVE orders." % label)
        if value == 14 and not fleet.has_wormhole_drive:
            raise CommandError("%s=wormhole requires a fleet with a wormhole drive." % label)
        return value

    def _parse_nonnegative_int(self, raw, label):
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise CommandError("Invalid %s value: %s" % (label, raw))
        if value < 0:
            raise CommandError("%s must be >= 0" % label)
        return value

    def _parse_remotemine_focus_keys(self, raw):
        if raw is None:
            return []
        tokens = [
            part.strip().lower()
            for part in str(raw).replace(";", ",").split(",")
            if part.strip()
        ]
        return [token for token in tokens if token in ALL_RESOURCE_KEYS]

    def _apply_transfer_defaults_if_empty(self, order, target_obj, target_kind):
        if order.transfer_type != "LOAD":
            return
        total_requested = (
            order.transfer_ironium
            + order.transfer_boranium
            + order.transfer_germanium
            + order.transfer_resource_x
            + order.transfer_resource_y
            + order.transfer_resource_z
            + order.transfer_colonists
        )
        if total_requested > 0:
            return
        if target_kind == "star":
            order.transfer_ironium = int(target_obj.ironium_inventory)
            order.transfer_boranium = int(target_obj.boranium_inventory)
            order.transfer_germanium = int(target_obj.germanium_inventory)
            order.transfer_resource_x = int(target_obj.resource_x_inventory)
            order.transfer_resource_y = int(target_obj.resource_y_inventory)
            order.transfer_resource_z = int(target_obj.resource_z_inventory)
            order.transfer_colonists = int(target_obj.colonists // 1000)
        elif target_kind == "fleet":
            order.transfer_ironium = int(target_obj.ironium_inventory)
            order.transfer_boranium = int(target_obj.boranium_inventory)
            order.transfer_germanium = int(target_obj.germanium_inventory)
            order.transfer_resource_x = int(target_obj.resource_x_inventory)
            order.transfer_resource_y = int(target_obj.resource_y_inventory)
            order.transfer_resource_z = int(target_obj.resource_z_inventory)
            order.transfer_colonists = int(target_obj.colonists)
        elif target_kind == "salvage":
            order.transfer_ironium = int(target_obj.ironium_inventory)
            order.transfer_boranium = int(target_obj.boranium_inventory)
            order.transfer_germanium = int(target_obj.germanium_inventory)
            order.transfer_resource_x = int(target_obj.resource_x_inventory)
            order.transfer_resource_y = int(target_obj.resource_y_inventory)
            order.transfer_resource_z = int(target_obj.resource_z_inventory)

    def _fleet_orders_summary(self, fleet):
        orders = fleet.orders.order_by("position", "id")
        payload = {}
        for order in orders:
            target_obj, target_x, target_y, target_kind = order.get_actual_target()
            order_data = {
                "position": order.position,
                "type": order.order_type,
                "repeat": bool(order.repeat),
                "target": {
                    "kind": target_kind,
                    "name": getattr(target_obj, "name", None),
                    "id": getattr(target_obj, "short_id", None),
                    "position": (
                        "(%s, %s)" % (target_x, target_y)
                        if target_x is not None and target_y is not None else None
                    ),
                },
                "warpfactor": order.warpfactor,
                "transfer": {
                    "type": order.transfer_type,
                    "ironium_kt": order.transfer_ironium,
                    "boranium_kt": order.transfer_boranium,
                    "germanium_kt": order.transfer_germanium,
                    "resource_x_kt": order.transfer_resource_x,
                    "resource_y_kt": order.transfer_resource_y,
                    "resource_z_kt": order.transfer_resource_z,
                    "colonists_kt": order.transfer_colonists,
                },
                "intercept_speed": order.intercept_speed,
                "patrol_radius": order.patrol_radius,
            }
            if order.order_type == "REMOTEMINE":
                focus_keys = self._parse_remotemine_focus_keys(order.remotemine_focus)
                if focus_keys:
                    order_data["remotemine_focus"] = ",".join(focus_keys)
                else:
                    order_data["remotemine_focus"] = "all"
                order_data["mine_until_full"] = bool(order.mine_until_full)
            if order.order_type == "BOMB":
                order_data["bomb_until"] = order.bomb_until
            payload[order.short_id] = order_data
        return payload

    def _handle_research_command(self, raw, player):
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            self.stdout.write("Invalid command syntax: %s" % exc)
            return

        if len(parts) == 1:
            self._print_yaml(self._research_overview_summary(player))
            return

        code = parts[1].strip().upper()
        category = ResearchCategory.objects.filter(enabled=True, code=code).first()
        if category is None:
            self.stdout.write("Unknown research category code: %s" % code)
            return

        if len(parts) == 2:
            self._print_yaml(self._research_category_summary(player, category))
            return

        if len(parts) == 3:
            if player.turned_in:
                self.stdout.write("Research allocations are locked after turn-in.")
                return
            try:
                requested_pct = float(parts[2])
            except ValueError:
                self.stdout.write("Invalid research allocation percentage: %s" % parts[2])
                return
            self._set_research_allocation(player, category, requested_pct)
            self._print_yaml(self._research_category_summary(player, category))
            return

        self.stdout.write("Usage: /research [CODE [PERCENT]]")

    def _research_overview_summary(self, player):
        rows = ensure_player_research_rows(player)
        budget = build_research_budget(player)
        data = build_research_screen_data(player)
        row_by_id = {row.id: row for row in data["rows"]}
        categories = {}
        for row in rows:
            screen_row = row_by_id.get(row.id, row)
            categories[row.category.code] = {
                "name": row.category.name,
                "current_level": float(row.current_level),
                "stored_rp": float(row.stored_rp),
                "allocation_percent": float(row.allocation_percent),
                "next_level_cost_rp": int(getattr(screen_row, "next_level_cost", 0) or 0),
                "next_level_progress_percent": int(
                    getattr(screen_row, "progress_percent", 0) or 0
                ),
            }
        return {
            "budget": budget,
            "singular_research": bool(player.singular_research),
            "categories": categories,
        }

    def _research_category_summary(self, player, category):
        data = build_research_screen_data(player, selected_category_id=category.id)
        selected = data.get("selected_research")
        upcoming = []
        for item in data.get("next_level_items") or []:
            upcoming.append({
                "name": item.get("name"),
                "description": item.get("description"),
                "tech_type": item.get("tech_type"),
                "params": item.get("params"),
            })
        payload = {
            "name": category.name,
            "current_level": (
                float(selected.current_level) if selected is not None else 0.0
            ),
            "stored_rp": float(selected.stored_rp) if selected is not None else 0.0,
            "allocation_percent": (
                float(selected.allocation_percent) if selected is not None else 0.0
            ),
            "next_level": data.get("next_level_number"),
            "next_level_cost_rp": data.get("next_level_cost"),
            "next_level_progress_percent": data.get("next_level_progress_percent"),
            "next_level_rp_per_year": data.get("next_level_rp_per_year"),
            "next_level_eta_years": data.get("next_level_eta_years"),
            "is_maxed": bool(data.get("selected_is_maxed")),
            "next_level_prerequisites": data.get("next_level_prerequisites"),
            "next_level_resource_requirements": data.get("next_level_resource_rows"),
            "upcoming_technologies": upcoming,
        }
        return {category.code: payload}

    def _set_research_allocation(self, player, category, requested_pct):
        rows = ensure_player_research_rows(player)
        if not rows:
            return

        if player.singular_research:
            if requested_pct > 0:
                set_singular_allocation(player, category.id)
            return

        target_pct = max(0.0, min(100.0, float(requested_pct)))
        row_by_cat = {row.category_id: row for row in rows}
        if category.id not in row_by_cat:
            raise CommandError("Category not available for player: %s" % category.code)

        other_rows = [row for row in rows if row.category_id != category.id]
        requested = {str(category.id): target_pct}
        remaining = max(0.0, 100.0 - target_pct)
        if not other_rows:
            requested[str(category.id)] = 100.0
            update_player_allocations(player, requested)
            return

        current_other_total = sum(float(row.allocation_percent or 0.0) for row in other_rows)
        if current_other_total > 0:
            for row in other_rows:
                share = float(row.allocation_percent or 0.0) / current_other_total
                requested[str(row.category_id)] = remaining * share
        else:
            even = remaining / float(len(other_rows))
            for row in other_rows:
                requested[str(row.category_id)] = even
        update_player_allocations(player, requested)

    def _handle_detail_command(self, raw, player):
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            self.stdout.write("Invalid command syntax: %s" % exc)
            return
        if len(parts) != 2:
            self.stdout.write('Usage: /detail <object_short_id_or_"Exact Name">')
            return
        selected = parts[1].strip()

        try:
            obj = self._resolve_detail_object(player, selected)
        except CommandError as exc:
            self.stdout.write(str(exc))
            return
        if obj is None:
            self.stdout.write("Object not found in this game: %s" % selected)
            return

        builder = DetailBuilder(player.game, selected=obj.short_id, player=player)
        detail = builder.build_detail()
        if not detail:
            self.stdout.write("No detail available for: %s" % selected)
            return
        detail = self._format_detail_for_cli(detail)
        self._print_yaml({obj.short_id: detail})

    def _resolve_detail_object(self, player, selected):
        selected = (selected or "").strip()
        obj = self._resolve_object_by_short_id(player, selected)
        if obj is not None:
            return obj
        return self._resolve_named_detail_object(player, selected)

    def _resolve_object_by_short_id(self, player, selected):
        short_id = (selected or "").strip().lower()
        if not self.SHORT_ID_RE.match(short_id):
            return None
        for obj in (
            Star.objects.filter(game=player.game, short_id=short_id).first(),
            Fleet.objects.filter(game=player.game, short_id=short_id).first(),
            player.game.salvages.filter(short_id=short_id).first(),
            player.game.anomalys.filter(short_id=short_id).first(),
        ):
            if isinstance(obj, Salvage) and getattr(player.game, "no_scanners", False):
                return obj
            if obj is not None and self._is_cli_object_discoverable(player, obj):
                return obj
        return None

    def _resolve_named_detail_object(self, player, selected_name):
        selected_name = (selected_name or "").strip()
        if not selected_name:
            return None
        matches = []
        for obj in self._iter_named_objects(player.game, selected_name):
            if self._object_is_name_visible_to_player(player, obj):
                matches.append(obj)
        return self._resolve_single_named_match(matches, selected_name)

    def _resolve_owned_rename_target(self, player, selector):
        selector = (selector or "").strip()
        obj = None
        if self.SHORT_ID_RE.match(selector.lower()):
            obj = (
                Star.objects.filter(game=player.game, player=player, short_id=selector.lower()).first() or
                Fleet.objects.filter(game=player.game, player=player, short_id=selector.lower()).first()
            )
            if obj is not None:
                return obj
        matches = list(
            Star.objects.filter(game=player.game, player=player, name__iexact=selector)
        ) + list(
            Fleet.objects.filter(game=player.game, player=player, name__iexact=selector)
        )
        return self._resolve_single_named_match(matches, selector)

    def _iter_named_objects(self, game, selected_name):
        for qs in (
            Star.objects.filter(game=game, name__iexact=selected_name).order_by("x", "y", "name", "id"),
            Fleet.objects.filter(game=game, name__iexact=selected_name).order_by("x", "y", "name", "id"),
            Anomaly.objects.filter(game=game, name__iexact=selected_name).order_by("x", "y", "name", "id"),
        ):
            for obj in qs:
                yield obj
        selected_name = str(selected_name or "").strip().lower()
        for obj in Salvage.objects.filter(game=game).order_by("x", "y", "id"):
            if str(obj.name).strip().lower() == selected_name:
                yield obj

    def _object_is_name_visible_to_player(self, player, obj):
        if isinstance(obj, Star):
            return True
        if isinstance(obj, Anomaly):
            return True
        return self._is_cli_object_discoverable(player, obj)

    def _is_cli_object_discoverable(self, player, obj):
        if isinstance(obj, (Star, Anomaly)):
            return True
        detail = DetailBuilder(player.game, selected=obj.short_id, player=player).build_detail()
        return bool(detail) and not bool(detail.get("unexplored"))

    def _resolve_single_named_match(self, matches, selector):
        if not matches:
            return None
        if len(matches) > 1:
            match_list = ", ".join(
                "%s <%s>" % (obj.__class__.__name__, obj.short_id)
                for obj in matches[:5]
            )
            raise CommandError(
                'Ambiguous name "%s". Matches: %s' % (selector, match_list)
            )
        return matches[0]

    def _format_detail_for_cli(self, detail):
        """Apply CLI-friendly numeric formatting to detail payload."""
        environmentals = detail.get("environmentals")
        if not isinstance(environmentals, dict):
            return detail
        for _label, env_data in environmentals.items():
            if not isinstance(env_data, dict):
                continue
            value = env_data.get("value")
            if isinstance(value, (float, int)):
                env_data["value"] = round(float(value), 2)
            for key, val in list(env_data.items()):
                if key.endswith("percent") and isinstance(val, (float, int)):
                    env_data[key] = round(float(val), 1)
        return detail

    def _handle_messages_command(self, raw, player, game):
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            self.stdout.write("Invalid command syntax: %s" % exc)
            return
        filters = {}
        for token in parts[1:]:
            if "=" not in token:
                self.stdout.write("Invalid filter token: %s" % token)
                return
            key, value = token.split("=", 1)
            filters[key.strip().lower()] = value.strip()
        try:
            payload = self._messages_summary(player, game, filters)
        except CommandError as exc:
            self.stdout.write(str(exc))
            return
        self._print_yaml(payload)

    def _messages_summary(self, player, game, filters):
        qs = self._messages_base_queryset(player)

        year = filters.get("year")
        if year is not None:
            try:
                qs = qs.filter(year=int(year))
            except ValueError:
                raise CommandError("Invalid year filter: %s" % year)

        since = filters.get("since")
        if since is not None:
            try:
                qs = qs.filter(year__gte=int(since))
            except ValueError:
                raise CommandError("Invalid since filter: %s" % since)

        category = filters.get("category")
        if category:
            qs = qs.filter(category=category.upper())

        priority = filters.get("priority")
        if priority is not None:
            if priority.lower() in ("1", "true", "yes", "y"):
                qs = qs.filter(priority=True)
            elif priority.lower() in ("0", "false", "no", "n"):
                qs = qs.filter(priority=False)
            else:
                raise CommandError("Invalid priority filter: %s" % priority)

        contains = filters.get("contains")
        if contains:
            qs = qs.filter(message__icontains=contains)

        limit = filters.get("limit", "50")
        try:
            limit = int(limit)
        except ValueError:
            raise CommandError("Invalid limit filter: %s" % limit)
        limit = max(1, min(limit, 500))

        payload = {}
        for msg in qs[:limit]:
            payload[msg.short_id] = {
                "year": msg.year,
                "category": msg.category,
                "priority": bool(msg.priority),
                "text": self._format_message_text_for_cli(msg.message),
            }
        return payload

    def _messages_base_queryset(self, player):
        qs = player.messages.order_by("-priority", "-year", "-id")
        if player.messages_seen_year is not None:
            qs = qs.filter(year__gte=player.messages_seen_year)
        return qs

    def _format_message_text_for_cli(self, message):
        text = str(message or "")

        def replace_link(match):
            href = html.unescape(match.group("href") or "")
            label = self._strip_html_tags(html.unescape(match.group("label") or ""))
            try:
                params = parse_qs(urlparse(href).query)
            except Exception:
                params = {}
            short_id = (params.get("sel") or [None])[0]
            if short_id:
                return "%s %s" % (label, self.CLI_SHORT_ID_TOKEN % short_id)
            return label

        text = self.HTML_LINK_RE.sub(replace_link, text)
        text = self._strip_html_tags(text)
        text = html.unescape(text)
        return re.sub(
            r"%s([0-9a-z]{12})__" % re.escape(self.CLI_SHORT_ID_TOKEN.split("%s")[0]),
            r"<\1>",
            text,
        ).strip()

    def _strip_html_tags(self, text):
        return self.HTML_TAG_RE.sub("", str(text or ""))

    def _print_yaml(self, payload):
        if yaml is None:
            self.stdout.write(str(payload))
            return
        dumped = yaml.safe_dump(payload, default_flow_style=False, sort_keys=False)
        self.stdout.write(dumped.rstrip())
