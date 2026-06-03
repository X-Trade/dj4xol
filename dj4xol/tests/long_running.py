import os
import random
import unittest
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import models
from django.test import TestCase
from django.urls import reverse

from ..ai_players import (
    AI_MODULE_EXPANSIONIST,
    AI_MODULE_IDLE,
    AI_MODULE_MICROMANAGER,
)
from ..colony_rules import calculate_employment_percent
from ..factory import GameFactory
from ..micromanager_rules import projected_mining_output
from ..mineral_rules import ALL_RESOURCE_KEYS
from ..models import (
    Account,
    Anomaly,
    Fleet,
    FleetOrders,
    Game,
    GameMessage,
    MicromanagerObjectState,
    ProductionOrder,
    Report,
    ResearchCategory,
    Salvage,
    ServerRace,
    ServerRaceType,
    ServerSettings,
    Star,
    Technology,
)
from ..research import (
    ensure_player_research_rows,
    sync_player_technology_unlocks_from_research,
)
from ..turn import GameTurn
from ._util import get_default_race, get_default_race_type


LONG_TEST_FLAG = os.environ.get("DJ4XOL_RUN_LONG_TESTS") == "1"


@unittest.skipUnless(LONG_TEST_FLAG, "Long-running test disabled (set DJ4XOL_RUN_LONG_TESTS=1).")
class LongRunningGameIsolationTest(TestCase):
    def setUp(self):
        get_default_race_type()
        self.user = User.objects.create_user("long_user", "long@test.com", "pass")
        self.account = Account.objects.create(django_user=self.user, alias="LongRunner")
        self.race = get_default_race()
        self._original_starting_fleets = self.race.starting_fleets
        self.addCleanup(self._restore_race_defaults)

    def _restore_race_defaults(self):
        if self.race.starting_fleets != self._original_starting_fleets:
            self.race.starting_fleets = self._original_starting_fleets
            self.race.save(update_fields=["starting_fleets"])

    def _run_play(self, *args):
        out = StringIO()
        call_command("play", *args, stdout=out)
        return out.getvalue()

    def _short_id_exists(self, game, short_id):
        return (
            Star.objects.filter(game=game, short_id=short_id).exists()
            or Fleet.objects.filter(game=game, short_id=short_id).exists()
            or Salvage.objects.filter(game=game, short_id=short_id).exists()
            or Anomaly.objects.filter(game=game, short_id=short_id).exists()
        )

    def _collect_map_short_ids(self, game):
        short_ids = []
        short_ids.extend(Star.objects.filter(game=game).values_list("short_id", flat=True))
        short_ids.extend(Fleet.objects.filter(game=game).values_list("short_id", flat=True))
        short_ids.extend(Salvage.objects.filter(game=game).values_list("short_id", flat=True))
        short_ids.extend(Anomaly.objects.filter(game=game).values_list("short_id", flat=True))
        return list(filter(None, short_ids))

    def test_large_scale_game_isolation_and_short_ids(self):
        game_count = int(os.environ.get("DJ4XOL_LONG_TEST_GAME_COUNT", 200))
        max_stars = int(os.environ.get("DJ4XOL_LONG_TEST_STAR_COUNT", 300))
        map_size = int(os.environ.get("DJ4XOL_LONG_TEST_MAP_SIZE", 500))
        starting_fleets = int(os.environ.get("DJ4XOL_LONG_TEST_STARTING_FLEETS", 200))
        extra_fleets = int(os.environ.get("DJ4XOL_LONG_TEST_EXTRA_FLEETS", 3))

        if self.race.starting_fleets != starting_fleets:
            self.race.starting_fleets = starting_fleets
            self.race.save(update_fields=["starting_fleets"])

        games = []
        for idx in range(game_count):
            factory = GameFactory()
            factory.game.name = "Long Game %s" % (idx + 1)
            factory.set_map_size(map_size, map_size)
            factory.set_owner(self.account)
            factory.create_stars(max_stars)
            game = factory.save()
            player = factory.join_player(self.account, self.race)
            self.assertIsNotNone(player, msg="Failed to join player for game %s" % game.short_id)
            for fleet_idx in range(extra_fleets):
                Fleet.objects.create(
                    game=game,
                    player=player,
                    name="Extra Fleet %s-%s" % (idx + 1, fleet_idx + 1),
                    x=player.homeworld.x,
                    y=player.homeworld.y,
                )
            games.append((game, player))

        for game, _player in games:
            short_ids = self._collect_map_short_ids(game)
            self.assertEqual(
                len(short_ids),
                len(set(short_ids)),
                msg="Short ID collision detected in game %s" % game.short_id,
            )

        game0, player0 = games[0]
        candidate_ids = list(
            Fleet.objects.filter(game=game0, player=player0).values_list("short_id", flat=True)
        ) or self._collect_map_short_ids(game0)
        shared_short_id = None
        for candidate in candidate_ids:
            if all(not self._short_id_exists(g, candidate) for g, _p in games[1:]):
                shared_short_id = candidate
                break
        self.assertIsNotNone(shared_short_id, msg="Unable to find shared short_id candidate.")

        shared_target_game0 = (
            Fleet.objects.filter(game=game0, short_id=shared_short_id).first()
            or Star.objects.filter(game=game0, short_id=shared_short_id).first()
            or Salvage.objects.filter(game=game0, short_id=shared_short_id).first()
            or Anomaly.objects.filter(game=game0, short_id=shared_short_id).first()
        )
        self.assertIsNotNone(shared_target_game0, msg="Shared short_id target missing in game 0.")
        shared_targets = {game0.id: shared_target_game0}
        for game, player in games[1:]:
            self.assertFalse(
                self._short_id_exists(game, shared_short_id),
                msg="Shared short_id already present in game %s" % game.short_id,
            )
            fleet = Fleet.objects.create(
                game=game,
                player=player,
                name="Shared Short ID Fleet",
                x=player.homeworld.x,
                y=player.homeworld.y,
                short_id=shared_short_id,
            )
            shared_targets[game.id] = fleet

        self.client.force_login(self.user)
        for game, player in games:
            target = shared_targets.get(game.id)
            response = self.client.get(
                reverse("dj4xol:game", args=[game.short_id]),
                {"sel": target.short_id},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(
                'data-selected-object-id="%s"' % target.short_id,
                response.content.decode("utf-8"),
            )
            output = self._run_play(
                game.short_id,
                "--no-auth",
                "--player",
                player.short_id,
                "--command",
                "/detail %s" % target.short_id,
            )
            self.assertIn(target.short_id, output)

        baseline = {}
        for game, _player in games:
            baseline[game.id] = {
                "year": game.year,
                "last_generated": game.last_generated,
                "next_generation": game.next_generation,
                "reports": Report.objects.filter(game=game).count(),
                "messages": GameMessage.objects.filter(game=game).count(),
                "fleets": Fleet.objects.filter(game=game).count(),
                "stars": Star.objects.filter(game=game).count(),
            }

        target_game = Game.objects.get(pk=game0.pk)
        GameTurn(target_game).generate_turn()

        for game, _player in games:
            refreshed = Game.objects.get(pk=game.pk)
            if refreshed.pk == target_game.pk:
                expected_year = baseline[game.id]["year"] + int(refreshed.years_per_turn or 1)
                self.assertEqual(refreshed.year, expected_year)
                self.assertNotEqual(refreshed.last_generated, baseline[game.id]["last_generated"])
                continue
            self.assertEqual(refreshed.year, baseline[game.id]["year"])
            self.assertEqual(refreshed.last_generated, baseline[game.id]["last_generated"])
            self.assertEqual(refreshed.next_generation, baseline[game.id]["next_generation"])
            self.assertFalse(refreshed.is_generating)
            self.assertEqual(Report.objects.filter(game=refreshed).count(), baseline[game.id]["reports"])
            self.assertEqual(GameMessage.objects.filter(game=refreshed).count(), baseline[game.id]["messages"])
            self.assertEqual(Fleet.objects.filter(game=refreshed).count(), baseline[game.id]["fleets"])
            self.assertEqual(Star.objects.filter(game=refreshed).count(), baseline[game.id]["stars"])


@unittest.skipUnless(LONG_TEST_FLAG, "Long-running test disabled (set DJ4XOL_RUN_LONG_TESTS=1).")
class LongRunningAIMicromanagerEconomyTest(TestCase):
    AI_YEARS = max(1, int(os.environ.get("DJ4XOL_LONG_TEST_AI_YEARS", 20)))

    def setUp(self):
        random.seed(12345)
        self.user = User.objects.create_user("long_ai_user", "long-ai@test.com", "pass")
        self.account = Account.objects.create(django_user=self.user, alias="LongAI")
        self._set_server_setting(
            "ai_check_in_turns",
            "1",
            "AI check-in interval for long-running tests",
        )
        self._set_server_setting(
            "ai_module_micromanager_enabled",
            "True",
            "Enable AI module: micromanager",
        )
        self._set_server_setting(
            "ai_module_expansionist_enabled",
            "True",
            "Enable AI module: expansionist",
        )
        self._set_server_setting(
            "ai_module_idle_enabled",
            "True",
            "Enable AI module: idle",
        )

    def _set_server_setting(self, key, value, description):
        ServerSettings.objects.update_or_create(
            key=key,
            defaults={
                "value": value,
                "long_value": value,
                "description": description,
            },
        )

    def _create_race_type(self, code, name, is_mechanical=False, ignores_all=False):
        race_type = ServerRaceType.objects.create(
            code=code,
            name=name,
            enabled=True,
            description="%s long-running AI test race type" % name,
            is_mechanical=bool(is_mechanical),
            ignores_gravity=bool(ignores_all),
            ignores_temperature=bool(ignores_all),
            ignores_radiation=bool(ignores_all),
        )
        return race_type

    def _create_race(
        self,
        name,
        race_type,
        starting_mines=2,
        starting_factories=4,
        starting_labs=0,
        starting_shipyards=1,
        starting_fleets=3,
        starting_tech_level=0,
        starting_colonists=24,
    ):
        return ServerRace.objects.create(
            name=name,
            plural_name="%ss" % name,
            homeworld_name="%s Prime" % name,
            race_type=race_type,
            owner=self.account,
            description="%s long-running AI test race" % name,
            starting_colonists=starting_colonists,
            starting_mines=starting_mines,
            starting_factories=starting_factories,
            starting_labs=starting_labs,
            starting_shipyards=starting_shipyards,
            starting_fleets=starting_fleets,
            starting_tech_level=starting_tech_level,
        )

    def _unlock_category_level(self, player, category, level):
        rows = ensure_player_research_rows(player)
        target = None
        for row in rows:
            if row.category_id == category.id:
                target = row
                break
        if target is None:
            raise AssertionError("Research row not created for category %s" % category.id)
        target.current_level = float(level)
        target.save(update_fields=["current_level"])
        sync_player_technology_unlocks_from_research(
            player,
            category_ids=[category.id],
            year=getattr(player.game, "year", 0),
        )
        return target

    def _create_administration_tech(self, player, code, tech_level, administration_level):
        category = ResearchCategory.objects.create(
            code=code,
            name="Long Administration %s" % administration_level,
            enabled=True,
        )
        build_cost = {
            1: {"bp": 120, "ironium": 350, "boranium": 0, "germanium": 250},
            2: {"bp": 90, "ironium": 225, "boranium": 0, "germanium": 325},
            3: {"bp": 70, "ironium": 175, "boranium": 0, "germanium": 250},
            4: {"bp": 60, "ironium": 100, "boranium": 0, "germanium": 260},
        }[administration_level]
        Technology.objects.create(
            category=category,
            level=tech_level,
            name="Administration %s" % administration_level,
            tech_type="INFRASTRUCTURE",
            params_json=(
                '{"administration_level": %s, "production_cost_overrides": '
                '{"BUILD_ADMINISTRATION": {"bp": %s, "ironium": %s, '
                '"boranium": %s, "germanium": %s, "colonists": 0}}}'
            ) % (
                administration_level,
                build_cost["bp"],
                build_cost["ironium"],
                build_cost["boranium"],
                build_cost["germanium"],
            ),
        )
        self._unlock_category_level(player, category, tech_level)
        return category

    def _build_ai_game(
        self,
        label,
        race,
        module_code,
        survivable_all=None,
        report_survivable=None,
        star_count=18,
        map_size=80,
        report_all=False,
    ):
        factory = GameFactory()
        factory.game.name = label
        factory.game.joinable = False
        factory.game.random_events = False
        factory.game.anomalies_enabled = False
        factory.game.years_per_turn = 1
        factory.set_map_size(map_size, map_size)
        factory.set_owner(self.account)
        factory.create_stars(star_count)
        game = factory.save()
        game.random_events = False
        game.anomalies_enabled = False
        game.save(update_fields=["random_events", "anomalies_enabled"])
        ai_player = factory.join_player(
            None,
            race,
            invited=True,
            is_ai=True,
            ai_module=module_code,
        )
        self.assertIsNotNone(ai_player)
        if survivable_all is None:
            survivable_all = bool(race.race_type.is_mechanical)
        if report_survivable is None:
            report_survivable = bool(survivable_all)
        self._prepare_observation_map(
            ai_player,
            survivable_all=bool(survivable_all),
            report_survivable=bool(report_survivable),
            report_all=bool(report_all),
        )
        return game, ai_player

    def _build_player_game(
        self,
        label,
        race,
        survivable_all=True,
        report_survivable=True,
        star_count=18,
        map_size=80,
        report_all=False,
    ):
        factory = GameFactory()
        factory.game.name = label
        factory.game.joinable = False
        factory.game.random_events = False
        factory.game.anomalies_enabled = False
        factory.game.years_per_turn = 1
        factory.set_map_size(map_size, map_size)
        factory.set_owner(self.account)
        factory.create_stars(star_count)
        game = factory.save()
        game.random_events = False
        game.anomalies_enabled = False
        game.save(update_fields=["random_events", "anomalies_enabled"])
        player = factory.join_player(self.account, race)
        self.assertIsNotNone(player)
        self._prepare_observation_map(
            player,
            survivable_all=bool(survivable_all),
            report_survivable=bool(report_survivable),
            report_all=bool(report_all),
        )
        return game, player

    def _grid_offsets(self, count, spacing=6):
        radius = 1
        offsets = []
        while len(offsets) < count:
            coords = set()
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if dx == 0 and dy == 0:
                        continue
                    coords.add((dx * spacing, dy * spacing))
            offsets = sorted(coords, key=lambda pair: (pair[0] * pair[0]) + (pair[1] * pair[1]))
            radius += 1
        return offsets[:count]

    def _prepare_observation_map(
        self,
        player,
        survivable_all=True,
        report_survivable=True,
        report_all=False,
    ):
        homeworld = player.homeworld
        homeworld.x = int(player.game.map_size_x / 2)
        homeworld.y = int(player.game.map_size_y / 2)
        homeworld.ironium_yield = 180
        homeworld.boranium_yield = 150
        homeworld.germanium_yield = 140
        homeworld.ironium_inventory = 120
        homeworld.boranium_inventory = 80
        homeworld.germanium_inventory = 80
        homeworld.save(update_fields=[
            "ironium_yield",
            "boranium_yield",
            "germanium_yield",
            "ironium_inventory",
            "boranium_inventory",
            "germanium_inventory",
            "x",
            "y",
        ])
        Fleet.objects.filter(game=player.game, player=player).update(
            x=homeworld.x,
            y=homeworld.y,
        )

        candidates = list(
            player.game.stars.exclude(id=homeworld.id).order_by("id")
        )
        if report_all:
            offsets = self._grid_offsets(len(candidates), spacing=6)
            nearby = candidates
        else:
            offsets = [(1, 0), (3, 1), (-3, 0), (0, -4), (5, 3), (-5, 3)]
            nearby = candidates[:len(offsets)]
        occupied = {(int(homeworld.x), int(homeworld.y))}
        for star, (dx, dy) in zip(nearby, offsets):
            target_x = int(homeworld.x) + dx
            target_y = int(homeworld.y) + dy
            while (target_x, target_y) in occupied:
                target_x += 1
                target_y += 1
            occupied.add((target_x, target_y))
            star.x = target_x
            star.y = target_y
            star.ironium_yield = 120
            star.boranium_yield = 100
            star.germanium_yield = 95
            star.ironium_inventory = 40
            star.boranium_inventory = 40
            star.germanium_inventory = 40
            if not survivable_all:
                star.gravity = float(player.gravity_center)
                star.temperature = float(player.temperature_center)
                star.radiation = float(player.radiation_center)
            star.save(update_fields=[
                "x",
                "y",
                "ironium_yield",
                "boranium_yield",
                "germanium_yield",
                "ironium_inventory",
                "boranium_inventory",
                "germanium_inventory",
                "gravity",
                "temperature",
                "radiation",
            ])

        for star in nearby:
            self._create_star_report(
                player.game,
                player,
                star,
                is_survivable=bool(report_survivable),
            )

    def _create_star_report(self, game, player, star, is_survivable=True):
        report, _created = Report.objects.update_or_create(
            game=game,
            player=player,
            target_type="star",
            target_id=star.id,
            defaults={
                "year": game.year,
                "cached_report": "{}",
            },
        )
        report.set_report_data({
            "name": star.name,
            "x": int(star.x),
            "y": int(star.y),
            "report_tier": "basic",
            "is_survivable": bool(is_survivable),
        })
        report.save(update_fields=["cached_report"])
        return report

    def _format_homeworld_orders(self, star):
        orders = list(
            star.production_orders.filter(added_by_micromanager=True)
            .order_by("position")
            .values_list("order_type", "quantity")
        )
        if not orders:
            return "<none>"
        return ", ".join("%s x%s" % (order_type, quantity) for order_type, quantity in orders)

    def _snapshot_homeworld(self, player, label):
        homeworld = Star.objects.get(pk=player.homeworld_id)
        mining_output = projected_mining_output(homeworld)
        total_mining_output = sum(int(value or 0) for value in mining_output.values())
        owned_stars = list(Star.objects.filter(game=player.game, player=player).order_by("id"))
        colony_count = len(owned_stars)
        fleet_count = Fleet.objects.filter(game=player.game, player=player).count()
        micromanager_star_state_count = MicromanagerObjectState.objects.filter(
            game=player.game,
            player=player,
            target_type=MicromanagerObjectState.TARGET_STAR,
        ).count()
        micromanager_fleet_state_count = MicromanagerObjectState.objects.filter(
            game=player.game,
            player=player,
            target_type=MicromanagerObjectState.TARGET_FLEET,
        ).count()
        homeworld_colonists = int(homeworld.colonists or 0)
        empire_mines = 0
        empire_factories = 0
        empire_labs = 0
        empire_defenses = 0
        empire_shipyards = 0
        empire_cities = 0
        empire_mining_output = 0
        empire_colonists = 0
        for owned_star in owned_stars:
            empire_colonists += int(getattr(owned_star, "colonists", 0) or 0)
            empire_mines += int(getattr(owned_star, "mines", 0) or 0)
            empire_factories += int(getattr(owned_star, "factories", 0) or 0)
            empire_labs += int(getattr(owned_star, "labs", 0) or 0)
            empire_defenses += int(getattr(owned_star, "defenses", 0) or 0)
            empire_shipyards += int(getattr(owned_star, "shipyards", 0) or 0)
            empire_cities += int(getattr(owned_star, "cities", 0) or 0)
            empire_mining_output += sum(
                int(value or 0) for value in projected_mining_output(owned_star).values()
            )
        snapshot = {
            "label": label,
            "year": int(player.game.year or 0),
            "colony_count": colony_count,
            "fleet_count": fleet_count,
            "micromanager_star_state_count": micromanager_star_state_count,
            "micromanager_fleet_state_count": micromanager_fleet_state_count,
            "employment_percent": float(calculate_employment_percent(homeworld)),
            "homeworld_colonists": homeworld_colonists,
            "homeworld_mines": int(homeworld.mines or 0),
            "homeworld_factories": int(homeworld.factories or 0),
            "homeworld_labs": int(homeworld.labs or 0),
            "homeworld_defenses": int(homeworld.defenses or 0),
            "homeworld_shipyards": int(homeworld.shipyards or 0),
            "homeworld_cities": int(homeworld.cities or 0),
            "empire_colonists": empire_colonists,
            "ironium_inventory": int(homeworld.ironium_inventory or 0),
            "boranium_inventory": int(homeworld.boranium_inventory or 0),
            "germanium_inventory": int(homeworld.germanium_inventory or 0),
            "ironium_yield": int(homeworld.ironium_yield or 0),
            "boranium_yield": int(homeworld.boranium_yield or 0),
            "germanium_yield": int(homeworld.germanium_yield or 0),
            "homeworld_mining_output": total_mining_output,
            "empire_mines": empire_mines,
            "empire_factories": empire_factories,
            "empire_labs": empire_labs,
            "empire_defenses": empire_defenses,
            "empire_shipyards": empire_shipyards,
            "empire_cities": empire_cities,
            "empire_mining_output": empire_mining_output,
            "orders": self._format_homeworld_orders(homeworld),
        }
        snapshot["line"] = (
            "[%s][%s] colonies=%s fleets=%s emp=%.1f%% pop=hw:%s empire:%s hw=mines:%s factories:%s "
            "labs:%s defenses:%s shipyards:%s cities:%s mining:%s empire=mines:%s factories:%s labs:%s "
            "defenses:%s shipyards:%s cities:%s mining:%s "
            "inv(I/B/G)=%s/%s/%s yields(I/B/G)=%s/%s/%s "
            "orders=%s"
        ) % (
            snapshot["label"],
            snapshot["year"],
            snapshot["colony_count"],
            snapshot["fleet_count"],
            snapshot["employment_percent"],
            snapshot["homeworld_colonists"],
            snapshot["empire_colonists"],
            snapshot["homeworld_mines"],
            snapshot["homeworld_factories"],
            snapshot["homeworld_labs"],
            snapshot["homeworld_defenses"],
            snapshot["homeworld_shipyards"],
            snapshot["homeworld_cities"],
            snapshot["homeworld_mining_output"],
            snapshot["empire_mines"],
            snapshot["empire_factories"],
            snapshot["empire_labs"],
            snapshot["empire_defenses"],
            snapshot["empire_shipyards"],
            snapshot["empire_cities"],
            snapshot["empire_mining_output"],
            snapshot["ironium_inventory"],
            snapshot["boranium_inventory"],
            snapshot["germanium_inventory"],
            snapshot["ironium_yield"],
            snapshot["boranium_yield"],
            snapshot["germanium_yield"],
            snapshot["orders"],
        )
        return snapshot

    def _run_ai_year_trace(self, player, years, label):
        snapshots = []
        initial_year = int(player.game.year or 0)
        initial_colonies = Star.objects.filter(game=player.game, player=player).count()
        expansion_year = None
        expansion_years = []
        duplicate_colonise_target_years = []
        previous_colony_count = initial_colonies

        opening = self._snapshot_homeworld(player, label)
        print(opening["line"])
        snapshots.append(opening)

        for _ in range(years):
            game = Game.objects.get(pk=player.game_id)
            GameTurn(game).generate_turn()
            player.refresh_from_db()
            player.game.refresh_from_db()
            snapshot = self._snapshot_homeworld(player, label)
            print(snapshot["line"])
            snapshots.append(snapshot)
            if expansion_year is None and snapshot["colony_count"] > initial_colonies:
                expansion_year = snapshot["year"]
            if snapshot["colony_count"] > previous_colony_count:
                expansion_years.append(snapshot["year"])
                previous_colony_count = snapshot["colony_count"]
            colonise_targets = list(
                FleetOrders.objects.filter(
                    game=game,
                    fleet__player=player,
                    order_type="COLONISE",
                    target_star_id__isnull=False,
                ).values_list("target_star_id", flat=True)
            )
            if len(colonise_targets) != len(set(colonise_targets)):
                duplicate_colonise_target_years.append(snapshot["year"])

        return {
            "snapshots": snapshots,
            "initial_year": initial_year,
            "initial_colonies": initial_colonies,
            "expansion_year": expansion_year,
            "expansion_years": expansion_years,
            "duplicate_colonise_target_years": duplicate_colonise_target_years,
        }

    def test_mechanical_micromanager_ai_expands_and_bootstraps_within_twenty_years(self):
        race_type = self._create_race_type(
            "MEC5",
            "MechFive",
            is_mechanical=True,
            ignores_all=True,
        )
        race = self._create_race(
            "MachinaFive",
            race_type,
            starting_mines=2,
            starting_factories=4,
            starting_labs=0,
            starting_shipyards=1,
            starting_fleets=3,
        )
        _game, ai_player = self._build_ai_game(
            "Mechanical Micromanager Long Test",
            race,
            AI_MODULE_MICROMANAGER,
        )

        result = self._run_ai_year_trace(
            ai_player,
            self.AI_YEARS,
            "mech-l5",
        )
        final = result["snapshots"][-1]
        initial_empire_colonists = int(result["snapshots"][0]["empire_colonists"] or 0)
        history = "\n".join(snapshot["line"] for snapshot in result["snapshots"])

        self.assertIsNotNone(result["expansion_year"], msg=history)
        self.assertLessEqual(
            int(result["expansion_year"] or 0),
            int(result["initial_year"] + self.AI_YEARS),
            msg=history,
        )
        self.assertGreater(
            max(
                int(snapshot["empire_colonists"] or 0)
                for snapshot in result["snapshots"]
            ),
            initial_empire_colonists,
            msg=history,
        )
        self.assertGreater(
            final["homeworld_mines"],
            int(race.starting_mines or 0),
            msg=history,
        )
        new_colonies = list(
            Star.objects.filter(game=ai_player.game, player=ai_player)
            .exclude(id=ai_player.homeworld_id)
            .order_by("id")
        )
        self.assertTrue(new_colonies, msg=history)
        for colony in new_colonies:
            surface_minerals = sum(
                int(getattr(colony, "%s_inventory" % key, 0) or 0)
                for key in ALL_RESOURCE_KEYS
            )
            mineral_yield = sum(
                int(getattr(colony, "%s_yield" % key, 0) or 0)
                for key in ALL_RESOURCE_KEYS
            )
            if mineral_yield <= 0 or surface_minerals >= 25000:
                continue
            has_mine_work = (
                int(getattr(colony, "mines", 0) or 0) > 0 or
                colony.production_orders.filter(order_type="BUILD_MINE").exists()
            )
            self.assertTrue(has_mine_work, msg=history)
        self.assertGreater(
            final["empire_mining_output"],
            result["snapshots"][0]["empire_mining_output"],
            msg=history,
        )
        self.assertGreater(final["empire_labs"], 0, msg=history)
        if final["empire_factories"] >= 10:
            self.assertGreaterEqual(
                final["empire_labs"] * 20,
                final["empire_factories"],
                msg=history,
            )

    def test_mechanical_micromanager_ai_keeps_hundred_year_homeworld_balanced(self):
        race_type = self._create_race_type(
            "MEC100",
            "MechHundred",
            is_mechanical=True,
            ignores_all=True,
        )
        race = self._create_race(
            "MachinaHundred",
            race_type,
            starting_mines=2,
            starting_factories=4,
            starting_labs=0,
            starting_shipyards=1,
            starting_fleets=3,
        )
        _game, ai_player = self._build_ai_game(
            "Mechanical Micromanager 100 Year Balance Test",
            race,
            AI_MODULE_MICROMANAGER,
        )

        result = self._run_ai_year_trace(
            ai_player,
            max(self.AI_YEARS, 100),
            "mech-l5-100",
        )
        final = result["snapshots"][-1]
        history = "\n".join(snapshot["line"] for snapshot in result["snapshots"])

        self.assertGreaterEqual(final["homeworld_shipyards"], 1, msg=history)
        self.assertGreaterEqual(final["homeworld_labs"], 10, msg=history)
        self.assertGreaterEqual(final["homeworld_defenses"], 10, msg=history)
        if final["homeworld_factories"] >= 100:
            self.assertGreaterEqual(final["homeworld_labs"], 50, msg=history)
            self.assertGreaterEqual(final["homeworld_defenses"], 50, msg=history)

    def test_mechanical_idle_ai_long_run_logs_homeworld_progress(self):
        race_type = self._create_race_type(
            "MEI3",
            "MechIdle",
            is_mechanical=True,
            ignores_all=True,
        )
        race = self._create_race(
            "MachinaIdle",
            race_type,
            starting_mines=2,
            starting_factories=4,
            starting_labs=0,
            starting_shipyards=1,
            starting_fleets=3,
        )
        _game, ai_player = self._build_ai_game(
            "Mechanical Idle Long Test",
            race,
            AI_MODULE_IDLE,
        )

        result = self._run_ai_year_trace(
            ai_player,
            self.AI_YEARS,
            "mech-l3",
        )
        final = result["snapshots"][-1]
        history = "\n".join(snapshot["line"] for snapshot in result["snapshots"])

        self.assertGreaterEqual(final["empire_mines"], 8, msg=history)
        self.assertGreaterEqual(final["empire_mining_output"], 80, msg=history)

    def test_level_three_micromanager_maintains_and_grows_existing_colonies(self):
        race_type = self._create_race_type(
            "MEL3X",
            "MechLevelThreeExisting",
            is_mechanical=True,
            ignores_all=True,
        )
        race = self._create_race(
            "MachinaLevelThreeExisting",
            race_type,
            starting_mines=4,
            starting_factories=6,
            starting_labs=0,
            starting_shipyards=1,
            starting_fleets=4,
            starting_colonists=60,
        )
        game, ai_player = self._build_ai_game(
            "Mechanical L3 Existing Colony Maintenance Long Test",
            race,
            AI_MODULE_IDLE,
            star_count=24,
            map_size=100,
            report_all=True,
        )

        seeded_colonies = list(
            game.stars.exclude(id=ai_player.homeworld_id).order_by("id")[:2]
        )
        for idx, colony in enumerate(seeded_colonies, start=1):
            colony.player = ai_player
            colony.colonists = 30_000 + (idx * 10_000)
            colony.mines = 2
            colony.factories = 3
            colony.labs = 0
            colony.defenses = 0
            colony.shipyards = 0
            colony.ironium_inventory = 80
            colony.boranium_inventory = 80
            colony.germanium_inventory = 80
            colony.ironium_yield = 110
            colony.boranium_yield = 100
            colony.germanium_yield = 95
            colony.gravity = float(ai_player.gravity_center)
            colony.temperature = float(ai_player.temperature_center)
            colony.radiation = float(ai_player.radiation_center)
            colony.save()
            colony.production_orders.all().delete()
            self._create_star_report(game, ai_player, colony, is_survivable=True)

        initial = self._snapshot_homeworld(ai_player, "l3-existing-initial")
        result = self._run_ai_year_trace(
            ai_player,
            max(self.AI_YEARS, 40),
            "l3-existing",
        )
        final = result["snapshots"][-1]
        history = "\n".join(snapshot["line"] for snapshot in result["snapshots"])

        for colony in seeded_colonies:
            colony.refresh_from_db()
            self.assertEqual(colony.player_id, ai_player.id, msg=history)
            self.assertGreater(int(colony.colonists or 0), 0, msg=history)

        self.assertGreaterEqual(final["colony_count"], initial["colony_count"], msg=history)
        self.assertGreaterEqual(
            final["empire_mines"] + final["empire_factories"],
            initial["empire_mines"] + initial["empire_factories"] + 6,
            msg=history,
        )
        self.assertGreaterEqual(final["empire_mining_output"], initial["empire_mining_output"], msg=history)
        self.assertTrue(
            MicromanagerObjectState.objects.filter(
                game=game,
                player=ai_player,
                target_type=MicromanagerObjectState.TARGET_STAR,
            ).exists(),
            msg=history,
        )

    def test_level_four_administration_delivers_resources_to_zero_yield_colonies(self):
        race_type = self._create_race_type(
            "MEL4R",
            "MechLevelFourResources",
            is_mechanical=True,
            ignores_all=True,
        )
        race = self._create_race(
            "MachinaLevelFourResources",
            race_type,
            starting_mines=0,
            starting_factories=8,
            starting_labs=0,
            starting_shipyards=1,
            starting_fleets=0,
            starting_colonists=100,
        )
        game, player = self._build_player_game(
            "Administration L4 Zero Yield Logistics Long Test",
            race,
            star_count=18,
            map_size=80,
            report_all=True,
        )
        self._create_administration_tech(player, "L4RES", 4, 4)

        source = Star.objects.get(pk=player.homeworld_id)
        source.has_administration = True
        source.colonists = 180_000
        source.mines = 10
        source.factories = 24
        source.labs = 0
        source.defenses = 4
        source.shipyards = 1
        source.ironium_inventory = 2_000
        source.boranium_inventory = 2_000
        source.germanium_inventory = 2_000
        source.ironium_yield = 150
        source.boranium_yield = 140
        source.germanium_yield = 130
        source.save()
        source.production_orders.all().delete()

        iron_star, lab_star = list(
            game.stars.exclude(id=source.id).order_by("id")[:2]
        )
        needy_specs = [
            (
                iron_star,
                {
                    "order_type": "BUILD_FACTORY",
                    "quantity": 8,
                    "ironium_yield": 0,
                    "boranium_yield": 95,
                    "germanium_yield": 95,
                    "ironium_inventory": 0,
                    "boranium_inventory": 240,
                    "germanium_inventory": 240,
                },
            ),
            (
                lab_star,
                {
                    "order_type": "BUILD_LAB",
                    "quantity": 6,
                    "ironium_yield": 95,
                    "boranium_yield": 0,
                    "germanium_yield": 0,
                    "ironium_inventory": 360,
                    "boranium_inventory": 0,
                    "germanium_inventory": 0,
                },
            ),
        ]
        initial_counts = {}
        for idx, (star, spec) in enumerate(needy_specs, start=1):
            star.player = player
            star.has_administration = True
            star.x = int(source.x) + (idx * 3)
            star.y = int(source.y)
            star.gravity = float(player.gravity_center)
            star.temperature = float(player.temperature_center)
            star.radiation = float(player.radiation_center)
            star.colonists = 100_000
            star.mines = 0
            star.factories = 12
            star.labs = 0
            star.defenses = 2
            star.shipyards = 0
            for resource_key in ALL_RESOURCE_KEYS:
                setattr(star, "%s_yield" % resource_key, 0)
                setattr(star, "%s_inventory" % resource_key, 0)
            for key, value in spec.items():
                if key not in ("order_type", "quantity"):
                    setattr(star, key, value)
            star.save()
            star.production_orders.all().delete()
            ProductionOrder.objects.create(
                game=game,
                star=star,
                order_type=spec["order_type"],
                quantity=spec["quantity"],
                position=1,
            )
            initial_counts[star.id] = {
                "factories": int(star.factories or 0),
                "labs": int(star.labs or 0),
            }
            Fleet.objects.create(
                game=game,
                player=player,
                name="Guard %s" % idx,
                x=star.x,
                y=star.y,
                ship_count=4,
                offense_level=4,
                defense_level=4,
                cargo_capacity=100,
                max_safe_warp=5,
                fuel=500,
                max_fuel=500,
            )
            Fleet.objects.create(
                game=game,
                player=player,
                name="Courier %s" % idx,
                x=star.x,
                y=star.y,
                ship_count=1,
                offense_level=0,
                defense_level=0,
                cargo_capacity=400,
                max_safe_warp=5,
                fuel=500,
                max_fuel=500,
            )

        history_lines = []
        saw_logistics_state = False
        for _ in range(max(self.AI_YEARS, 24)):
            GameTurn(Game.objects.get(pk=game.pk)).generate_turn()
            game.refresh_from_db()
            iron_star.refresh_from_db()
            lab_star.refresh_from_db()
            saw_logistics_state = saw_logistics_state or MicromanagerObjectState.objects.filter(
                game=game,
                player=player,
                target_type=MicromanagerObjectState.TARGET_FLEET,
                mission__startswith="logistics",
            ).exists()
            history_lines.append(
                "[%s] iron inv=%s factories=%s lab inv(B/G)=%s/%s labs=%s orders=%s/%s"
                % (
                    game.year,
                    iron_star.ironium_inventory,
                    iron_star.factories,
                    lab_star.boranium_inventory,
                    lab_star.germanium_inventory,
                    lab_star.labs,
                    self._format_homeworld_orders(iron_star),
                    self._format_homeworld_orders(lab_star),
                )
            )

        history = "\n".join(history_lines)
        iron_order_progress = ProductionOrder.objects.filter(star=iron_star).aggregate(
            spent=models.Sum("spent_ironium")
        )["spent"] or 0
        lab_order_progress = ProductionOrder.objects.filter(star=lab_star).aggregate(
            spent_bor=models.Sum("spent_boranium"),
            spent_germ=models.Sum("spent_germanium"),
        )
        iron_received_or_spent = (
            int(iron_star.ironium_inventory or 0) +
            int(iron_order_progress or 0) +
            max(0, int(iron_star.factories or 0) - initial_counts[iron_star.id]["factories"]) * 20
        )
        boranium_received_or_spent = (
            int(lab_star.boranium_inventory or 0) +
            int(lab_order_progress["spent_bor"] or 0) +
            max(0, int(lab_star.labs or 0) - initial_counts[lab_star.id]["labs"]) * 20
        )
        germanium_received_or_spent = (
            int(lab_star.germanium_inventory or 0) +
            int(lab_order_progress["spent_germ"] or 0) +
            max(0, int(lab_star.labs or 0) - initial_counts[lab_star.id]["labs"]) * 20
        )

        self.assertGreater(iron_received_or_spent, 0, msg=history)
        self.assertGreater(boranium_received_or_spent, 0, msg=history)
        self.assertGreater(germanium_received_or_spent, 0, msg=history)
        self.assertTrue(saw_logistics_state, msg=history)

    def test_default_joat_micromanager_ai_expands_steadily_after_bootstrap(self):
        race_type = ServerRaceType.objects.get(code="JOAT")
        race = ServerRace.objects.create(
            name="LongJoat",
            plural_name="LongJoats",
            homeworld_name="Long Joat Prime",
            race_type=race_type,
            owner=self.account,
            description="Default JOAT long-running AI test race",
        )
        _game, ai_player = self._build_ai_game(
            "JOAT Micromanager Long Test",
            race,
            AI_MODULE_MICROMANAGER,
            survivable_all=False,
            report_survivable=True,
        )

        years = max(self.AI_YEARS, 40)
        result = self._run_ai_year_trace(
            ai_player,
            years,
            "joat-l5",
        )
        final = result["snapshots"][-1]
        history = "\n".join(snapshot["line"] for snapshot in result["snapshots"])

        self.assertIsNotNone(result["expansion_year"], msg=history)
        self.assertLessEqual(
            int(result["expansion_year"] or 0),
            int(result["initial_year"] + 20),
            msg=history,
        )
        self.assertGreaterEqual(
            len(result["expansion_years"]),
            2,
            msg=history,
        )
        self.assertGreaterEqual(final["colony_count"], 3, msg=history)

    def test_default_joat_expansionist_ai_reaches_twenty_colonies_within_hundred_years(self):
        race_type = ServerRaceType.objects.get(code="JOAT")
        race = ServerRace.objects.create(
            name="LongJoatExpansion",
            plural_name="LongJoatExpansions",
            homeworld_name="Long Joat Expansion Prime",
            race_type=race_type,
            owner=self.account,
            description="Default JOAT expansionist AI long-running test race",
        )
        _game, ai_player = self._build_ai_game(
            "JOAT Expansionist Long Test",
            race,
            AI_MODULE_EXPANSIONIST,
            survivable_all=False,
            report_survivable=True,
            star_count=64,
            map_size=180,
            report_all=True,
        )

        years = max(self.AI_YEARS, 100)
        result = self._run_ai_year_trace(
            ai_player,
            years,
            "joat-exp",
        )
        final = result["snapshots"][-1]
        history = "\n".join(snapshot["line"] for snapshot in result["snapshots"])
        expansion_years = list(result["expansion_years"])

        self.assertGreaterEqual(final["colony_count"], 20, msg=history)
        self.assertGreaterEqual(final["empire_labs"], 1000, msg=history)
        self.assertGreaterEqual(final["empire_defenses"], 1000, msg=history)
        self.assertFalse(
            result["duplicate_colonise_target_years"],
            msg=history,
        )
        self.assertGreater(
            final["empire_colonists"],
            result["snapshots"][0]["empire_colonists"],
            msg=history,
        )
        self.assertTrue(expansion_years, msg=history)
        self.assertLessEqual(
            int(expansion_years[0]),
            int(result["initial_year"] + 20),
            msg=history,
        )
        for previous_year, year in zip(expansion_years, expansion_years[1:]):
            self.assertLessEqual(
                int(year - previous_year),
                9,
                msg=history,
            )

    def test_expansionist_ai_explores_unknown_map_over_forty_years(self):
        race_type = self._create_race_type(
            "MEXP",
            "MechExplore",
            is_mechanical=True,
            ignores_all=True,
        )
        race = self._create_race(
            "MachinaExplore",
            race_type,
            starting_mines=2,
            starting_factories=4,
            starting_labs=0,
            starting_shipyards=1,
            starting_fleets=6,
            starting_colonists=50,
        )
        _game, ai_player = self._build_ai_game(
            "Expansionist Exploration Long Test",
            race,
            AI_MODULE_EXPANSIONIST,
            star_count=32,
            map_size=140,
            report_all=False,
        )
        Fleet.objects.filter(game=ai_player.game, player=ai_player).update(
            basic_scanner_range=8
        )
        initial_reports = Report.objects.filter(
            game=ai_player.game,
            player=ai_player,
            target_type="star",
        ).count()

        result = self._run_ai_year_trace(
            ai_player,
            max(self.AI_YEARS, 40),
            "exp-explore",
        )
        final_reports = Report.objects.filter(
            game=ai_player.game,
            player=ai_player,
            target_type="star",
        ).count()
        history = "\n".join(snapshot["line"] for snapshot in result["snapshots"])

        self.assertGreaterEqual(final_reports, initial_reports + 5, msg=history)
        self.assertTrue(
            MicromanagerObjectState.objects.filter(
                game=ai_player.game,
                player=ai_player,
                target_type=MicromanagerObjectState.TARGET_STAR,
                mission="colony_role",
            ).exists(),
            msg=history,
        )
        self.assertTrue(
            max(
                snapshot["micromanager_fleet_state_count"]
                for snapshot in result["snapshots"]
            ) > 0,
            msg=history,
        )
        self.assertFalse(
            result["duplicate_colonise_target_years"],
            msg=history,
        )
