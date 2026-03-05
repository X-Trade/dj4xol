import os
import unittest
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from ..factory import GameFactory
from ..models import (
    Account,
    Anomaly,
    Fleet,
    Game,
    GameMessage,
    Report,
    Salvage,
    Star,
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
