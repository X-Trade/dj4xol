"""Tests for the exploration reports feature."""
import json

from django.test import TestCase
from django.contrib.auth.models import User
from ..models import (
    Account, Star, Fleet, FleetOrders, Salvage, Report, Anomaly, GameMessage,
    PlayerDiplomaticStance,
)
from ..factory import GameFactory
from ..objectdetails import DetailBuilder
from ..turn import (
    GameTurn,
    format_basic_hidden_salvage_name,
    format_basic_unknown_fleet_name,
)
from ._util import get_default_race_type, get_default_race, default_game


def create_test_game(account, stars=5):
    """Create a test game with the given account as owner and player."""
    factory = GameFactory()
    factory.set_map_size(100, 100)
    factory.set_owner(account)
    factory.create_stars(stars)
    game = factory.save()
    player = factory.join_player(account, get_default_race())
    return game, player, factory


class ReportModelTest(TestCase):
    """Tests for the Report model itself."""

    def setUp(self):
        get_default_race_type()
        self.user = User.objects.create_user('testuser_rm', 'test@test.com', 'pass')
        self.account = Account.objects.create(django_user=self.user)
        self.game, self.player, _ = create_test_game(self.account, stars=5)
        self.star = Star.objects.filter(game=self.game).first()

    def test_create_report(self):
        """Reports can be created for game objects."""
        report = Report.objects.create(
            game=self.game,
            player=self.player,
            year=2400,
            target_type='star',
            target_id=self.star.id,
            cached_report='{}'
        )
        self.assertEqual(report.player, self.player)
        self.assertEqual(report.target_type, 'star')

    def test_set_and_get_report_data(self):
        """Report data can be serialised and deserialised."""
        report = Report.objects.create(
            game=self.game,
            player=self.player,
            year=2400,
            target_type='star',
            target_id=self.star.id,
            cached_report='{}'
        )
        data = {'name': 'Test Star', 'colonists': 1000}
        report.set_report_data(data)
        report.save()

        report.refresh_from_db()
        retrieved = report.get_report_data()
        self.assertEqual(retrieved['name'], 'Test Star')
        self.assertEqual(retrieved['colonists'], 1000)

    def test_unique_constraint(self):
        """Only one report per player per target."""
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=2400,
            target_type='star',
            target_id=self.star.id,
            cached_report='{}'
        )
        # Creating another should fail
        with self.assertRaises(Exception):
            Report.objects.create(
                game=self.game,
                player=self.player,
                year=2401,
                target_type='star',
                target_id=self.star.id,
                cached_report='{}'
            )


class VisibilityTest(TestCase):
    """Tests for visibility rules in DetailBuilder."""

    def setUp(self):
        get_default_race_type()
        self.user1 = User.objects.create_user('player1_vis', 'p1@test.com', 'pass')
        self.account1 = Account.objects.create(django_user=self.user1)
        self.user2 = User.objects.create_user('player2_vis', 'p2@test.com', 'pass')
        self.account2 = Account.objects.create(django_user=self.user2)

        # Create game with account1 as owner
        factory = GameFactory()
        factory.set_map_size(100, 100)
        factory.set_owner(self.account1)
        factory.create_stars(10)
        self.game = factory.save()
        self.game.joinable = True  # Allow second player to join
        self.game.save()
        self.player1 = factory.join_player(self.account1, get_default_race())
        self.player2 = factory.join_player(self.account2, get_default_race())

        # Get an unowned star (not player1's homeworld)
        self.unowned_star = Star.objects.filter(
            game=self.game, player__isnull=True
        ).first()

        # Assign one to player1 manually
        self.owned_star = Star.objects.filter(
            game=self.game, player__isnull=True
        ).exclude(id=self.unowned_star.id).first()
        self.owned_star.player = self.player1
        self.owned_star.colonists = 1000
        self.owned_star.save()

    def test_can_view_owned_object(self):
        """Player can view objects they own."""
        builder = DetailBuilder(
            self.game,
            x=self.owned_star.x,
            y=self.owned_star.y,
            player=self.player1
        )
        can_view, year = builder.can_view_object(builder.selected_obj)
        self.assertTrue(can_view)
        self.assertIsNone(year)

    def test_cannot_view_unvisited_object(self):
        """Player cannot view unvisited objects."""
        builder = DetailBuilder(
            self.game,
            x=self.unowned_star.x,
            y=self.unowned_star.y,
            player=self.player2
        )
        can_view, year = builder.can_view_object(builder.selected_obj)
        self.assertFalse(can_view)

    def test_can_view_with_fleet_present(self):
        """Player can view objects where they have a fleet."""
        Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Scout Fleet',
            x=self.unowned_star.x,
            y=self.unowned_star.y
        )

        builder = DetailBuilder(
            self.game,
            x=self.unowned_star.x,
            y=self.unowned_star.y,
            player=self.player2
        )
        can_view, year = builder.can_view_object(builder.selected_obj)
        self.assertTrue(can_view)
        self.assertIsNone(year)

    def test_can_view_with_cached_report(self):
        """Player can view objects they have a cached report for."""
        Report.objects.create(
            game=self.game,
            player=self.player2,
            year=2400,
            target_type='star',
            target_id=self.unowned_star.id,
            cached_report='{"name": "Old Name"}'
        )

        builder = DetailBuilder(
            self.game,
            x=self.unowned_star.x,
            y=self.unowned_star.y,
            player=self.player2
        )
        can_view, year = builder.can_view_object(builder.selected_obj)
        self.assertTrue(can_view)
        self.assertEqual(year, 2400)


class UnexploredDetailTest(TestCase):
    """Tests for unexplored object display."""

    def setUp(self):
        get_default_race_type()
        self.user = User.objects.create_user('testuser_unex', 'test@test.com', 'pass')
        self.account = Account.objects.create(django_user=self.user)
        self.game, self.player, _ = create_test_game(self.account, stars=10)

        # Get a star that player doesn't own and has no fleet at
        self.distant_star = Star.objects.filter(
            game=self.game, player__isnull=True
        ).first()

    def test_unexplored_detail_structure(self):
        """Unexplored objects return minimal detail with unexplored flag."""
        builder = DetailBuilder(
            self.game,
            x=self.distant_star.x,
            y=self.distant_star.y,
            player=self.player
        )
        detail = builder.build_detail()

        self.assertTrue(detail['unexplored'])
        self.assertEqual(detail['name'], self.distant_star.name)
        self.assertTrue(detail['is_star'])
        self.assertNotIn('population', detail)
        self.assertNotIn('environmentals', detail)
        self.assertNotIn('resources', detail)

    def test_salvage_is_hidden_without_report(self):
        salvage = Salvage.objects.create(
            game=self.game,
            x=self.distant_star.x,
            y=self.distant_star.y,
            ironium_inventory=25,
            boranium_inventory=10,
            germanium_inventory=5,
        )

        detail = DetailBuilder(
            self.game,
            x=self.distant_star.x,
            y=self.distant_star.y,
            player=self.player,
        ).build_detail()

        objects_here = detail.get('objects_here') or []
        self.assertFalse(any(obj.get('short_id') == salvage.short_id for obj in objects_here))

        hidden = DetailBuilder(
            self.game,
            selected=salvage.short_id.lower(),
            player=self.player,
        ).build_detail()
        self.assertIsNone(hidden)

    def test_no_scanners_shows_salvage_as_unexplored_without_report(self):
        self.game.no_scanners = True
        self.game.save(update_fields=['no_scanners'])
        salvage = Salvage.objects.create(
            game=self.game,
            x=self.distant_star.x,
            y=self.distant_star.y,
            ironium_inventory=25,
            boranium_inventory=10,
            germanium_inventory=5,
        )

        detail = DetailBuilder(
            self.game,
            x=self.distant_star.x,
            y=self.distant_star.y,
            player=self.player,
        ).build_detail()
        objects_here = detail.get('objects_here') or []
        self.assertTrue(any(obj.get('short_id') == salvage.short_id for obj in objects_here))

        hidden = DetailBuilder(
            self.game,
            selected=salvage.short_id.lower(),
            player=self.player,
        ).build_detail()
        self.assertTrue(hidden['unexplored'])
        self.assertEqual(hidden['selected_id'], salvage.short_id)


class ReportGenerationTest(TestCase):
    """Tests for report generation during turn processing."""

    def setUp(self):
        get_default_race_type()
        self.user = User.objects.create_user('testuser_gen', 'test@test.com', 'pass')
        self.account = Account.objects.create(django_user=self.user)
        self.game, self.player, _ = create_test_game(self.account, stars=10)

        # Get unowned stars for testing
        self.star1 = Star.objects.filter(game=self.game, player__isnull=True).first()
        self.star2 = Star.objects.filter(
            game=self.game, player__isnull=True
        ).exclude(id=self.star1.id).first()

    def test_report_generated_for_fleet_at_star(self):
        """Reports are generated when a fleet is at a star location."""
        Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Explorer',
            x=self.star1.x,
            y=self.star1.y
        )

        turn = GameTurn(self.game)
        turn.generate_reports()

        report = Report.objects.filter(
            player=self.player,
            target_type='star',
            target_id=self.star1.id
        ).first()
        self.assertIsNotNone(report)
        self.assertEqual(report.year, self.game.year)

    def test_report_contains_star_data(self):
        """Star reports contain expected data."""
        self.star1.colonists = 5000
        self.star1.mines = 12
        self.star1.factories = 9
        self.star1.labs = 7
        self.star1.defenses = 3
        self.star1.shipyards = 2
        self.star1.gravity = 1.5
        self.star1.temperature = 0.8
        self.star1.radiation = 1.2
        self.star1.ironium_yield = 55
        self.star1.boranium_yield = 45
        self.star1.germanium_yield = 35
        self.star1.ironium_inventory = 1200
        self.star1.boranium_inventory = 800
        self.star1.germanium_inventory = 600
        self.star1.save()

        Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Explorer',
            x=self.star1.x,
            y=self.star1.y
        )

        turn = GameTurn(self.game)
        turn.generate_reports()

        report = Report.objects.get(
            player=self.player,
            target_type='star',
            target_id=self.star1.id
        )
        data = report.get_report_data()

        self.assertEqual(data['name'], self.star1.name)
        self.assertEqual(data['colonists'], 5000)
        self.assertEqual(data['gravity'], 1.5)
        self.assertEqual(data['temperature'], 0.8)
        self.assertEqual(data['radiation'], 1.2)
        self.assertEqual(data['ironium_yield'], 55)
        self.assertEqual(data['boranium_yield'], 45)
        self.assertEqual(data['germanium_yield'], 35)
        self.assertEqual(data['ironium_inventory'], 1200)
        self.assertEqual(data['boranium_inventory'], 800)
        self.assertEqual(data['germanium_inventory'], 600)
        self.assertEqual(data['mines'], 12)
        self.assertEqual(data['factories'], 9)
        self.assertEqual(data['labs'], 7)
        self.assertEqual(data['defenses'], 3)
        self.assertEqual(data['shipyards'], 2)
        self.assertIn('factories_bp', data)
        self.assertIn('labs_rp', data)

    def test_report_overwrites_previous(self):
        """New reports overwrite previous ones for the same target."""
        Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Explorer',
            x=self.star1.x,
            y=self.star1.y
        )

        turn = GameTurn(self.game)
        turn.generate_reports()

        first_year = Report.objects.get(
            player=self.player,
            target_type='star',
            target_id=self.star1.id
        ).year

        # Advance year and regenerate
        self.game.year += 1
        self.game.save()
        turn.generate_reports()

        reports = Report.objects.filter(
            player=self.player,
            target_type='star',
            target_id=self.star1.id
        )
        self.assertEqual(reports.count(), 1)
        self.assertEqual(reports.first().year, first_year + 1)

    def test_cached_star_detail_includes_resource_yields(self):
        """Cached star detail should include resource yields and surfaces."""
        self.star1.ironium_yield = 61
        self.star1.boranium_yield = 42
        self.star1.germanium_yield = 27
        self.star1.ironium_inventory = 1500
        self.star1.boranium_inventory = 900
        self.star1.germanium_inventory = 400
        self.star1.save()

        Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Explorer',
            x=self.star1.x,
            y=self.star1.y
        )
        GameTurn(self.game).generate_reports()

        # Move fleet away so detail renders from cached report instead of current data.
        fleet = Fleet.objects.filter(game=self.game, player=self.player).first()
        fleet.x = 1 if self.star1.x != 1 else 2
        fleet.y = 1 if self.star1.y != 1 else 2
        fleet.save()

        detail = DetailBuilder(
            self.game, x=self.star1.x, y=self.star1.y,
            selected=self.star1.short_id.lower(), player=self.player
        ).build_detail()

        self.assertIn('resources', detail)
        self.assertEqual(detail['resources']['ironium']['yield'], 61)
        self.assertEqual(detail['resources']['ironium']['surface'], 1500)
        self.assertEqual(detail['resources']['boranium']['yield'], 42)
        self.assertEqual(detail['resources']['germanium']['yield'], 27)

    def test_cached_star_detail_includes_infrastructure(self):
        """Cached star detail should include infrastructure values from report."""
        self.star1.mines = 11
        self.star1.factories = 8
        self.star1.labs = 6
        self.star1.defenses = 4
        self.star1.shipyards = 2
        self.star1.colonists = 4500
        self.star1.save()

        Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Explorer',
            x=self.star1.x,
            y=self.star1.y
        )
        GameTurn(self.game).generate_reports()

        # Move fleet away so detail reads from cached report.
        fleet = Fleet.objects.filter(game=self.game, player=self.player).first()
        fleet.x = 1 if self.star1.x != 1 else 2
        fleet.y = 1 if self.star1.y != 1 else 2
        fleet.save()

        detail = DetailBuilder(
            self.game, x=self.star1.x, y=self.star1.y,
            selected=self.star1.short_id.lower(), player=self.player
        ).build_detail()

        self.assertIn('infrastructure', detail)
        self.assertEqual(detail['infrastructure']['Mines'], 11)
        self.assertEqual(detail['infrastructure']['Factories'], 8)
        self.assertEqual(detail['infrastructure']['Labs'], 6)
        self.assertEqual(detail['infrastructure']['Defenses'], 4)
        self.assertEqual(detail['infrastructure']['Shipyards'], 2)

    def test_reports_generated_for_all_objects_at_location(self):
        """Reports generated for multiple objects at the same location."""
        salvage = Salvage.objects.create(
            game=self.game,
            x=self.star1.x,
            y=self.star1.y,
            ironium_inventory=100,
            boranium_inventory=50,
            germanium_inventory=25
        )

        Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Explorer',
            x=self.star1.x,
            y=self.star1.y
        )

        turn = GameTurn(self.game)
        turn.generate_reports()

        star_report = Report.objects.filter(
            player=self.player,
            target_type='star',
            target_id=self.star1.id
        ).first()
        salvage_report = Report.objects.filter(
            player=self.player,
            target_type='salvage',
            target_id=salvage.id
        ).first()

        self.assertIsNotNone(star_report)
        self.assertIsNotNone(salvage_report)

    def test_cached_salvage_detail_includes_full_inventory(self):
        """Cached salvage reports should preserve per-mineral inventory values."""
        salvage = Salvage.objects.create(
            game=self.game,
            x=self.star1.x,
            y=self.star1.y,
            ironium_inventory=130,
            boranium_inventory=70,
            germanium_inventory=20,
        )

        Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Explorer',
            x=self.star1.x,
            y=self.star1.y
        )
        GameTurn(self.game).generate_reports()

        # Move fleet away so detail renders from cached report.
        fleet = Fleet.objects.filter(game=self.game, player=self.player).first()
        fleet.x = 1 if self.star1.x != 1 else 2
        fleet.y = 1 if self.star1.y != 1 else 2
        fleet.save()

        detail = DetailBuilder(
            self.game, x=self.star1.x, y=self.star1.y,
            selected=salvage.short_id.lower(), player=self.player
        ).build_detail()

        self.assertIn('salvage_inventory', detail)
        items = {item['label']: item['amount'] for item in detail['salvage_inventory']['items']}
        self.assertEqual(items['Ironium'], 130)
        self.assertEqual(items['Boranium'], 70)
        self.assertEqual(items['Germanium'], 20)
        self.assertEqual(detail['salvage_inventory']['total'], 220)
        self.assertFalse(detail['salvage_inventory']['composition_unknown'])

    def test_report_on_other_player_fleet(self):
        """Reports generated for enemy fleets at the same location."""
        # Create second player
        user2 = User.objects.create_user('player2_gen', 'p2@test.com', 'pass')
        account2 = Account.objects.create(django_user=user2)
        self.game.joinable = True
        self.game.save()

        factory = GameFactory(game=self.game)
        player2 = factory.join_player(account2, get_default_race())

        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=player2,
            name='Enemy Ship',
            x=self.star1.x,
            y=self.star1.y,
            ship_count=5
        )

        Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Our Scout',
            x=self.star1.x,
            y=self.star1.y
        )

        turn = GameTurn(self.game)
        turn.generate_reports()

        fleet_report = Report.objects.filter(
            player=self.player,
            target_type='fleet',
            target_id=enemy_fleet.id
        ).first()
        self.assertIsNotNone(fleet_report)
        data = fleet_report.get_report_data()
        self.assertEqual(data['ship_count'], 5)


class ReportPrivacyTest(TestCase):
    """Tests ensuring players cannot access other players' reports."""

    def setUp(self):
        get_default_race_type()
        self.user1 = User.objects.create_user('player1_priv', 'p1@test.com', 'pass')
        self.account1 = Account.objects.create(django_user=self.user1)
        self.user2 = User.objects.create_user('player2_priv', 'p2@test.com', 'pass')
        self.account2 = Account.objects.create(django_user=self.user2)

        factory = GameFactory()
        factory.set_map_size(100, 100)
        factory.set_owner(self.account1)
        factory.create_stars(10)
        self.game = factory.save()
        self.game.joinable = True
        self.game.save()
        self.player1 = factory.join_player(self.account1, get_default_race())
        self.player2 = factory.join_player(self.account2, get_default_race())

        self.star = Star.objects.filter(game=self.game, player__isnull=True).first()

    def test_report_only_visible_to_owner(self):
        """Reports are only used for visibility by the player who owns them."""
        Report.objects.create(
            game=self.game,
            player=self.player1,
            year=2400,
            target_type='star',
            target_id=self.star.id,
            cached_report='{"name": "Explored Star"}'
        )

        builder1 = DetailBuilder(
            self.game,
            x=self.star.x,
            y=self.star.y,
            player=self.player1
        )
        can_view1, year1 = builder1.can_view_object(builder1.selected_obj)
        self.assertTrue(can_view1)
        self.assertEqual(year1, 2400)

        builder2 = DetailBuilder(
            self.game,
            x=self.star.x,
            y=self.star.y,
            player=self.player2
        )
        can_view2, year2 = builder2.can_view_object(builder2.selected_obj)
        self.assertFalse(can_view2)


class CachedReportDisplayTest(TestCase):
    """Tests for displaying cached report data."""

    def setUp(self):
        get_default_race_type()
        self.user = User.objects.create_user('testuser_disp', 'test@test.com', 'pass')
        self.account = Account.objects.create(django_user=self.user)
        self.game, self.player, _ = create_test_game(self.account, stars=10)

        self.star = Star.objects.filter(game=self.game, player__isnull=True).first()

    def test_cached_report_shows_historical_data(self):
        """When viewing from cache, shows cached data not current state."""
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=2400,
            target_type='star',
            target_id=self.star.id,
            cached_report='{"name": "Old Name", "colonists": 1000, '
                         '"gravity": 1.0, "temperature": 1.0, "radiation": 1.0}'
        )

        self.star.name = 'New Name'
        self.star.colonists = 5000
        self.star.save()

        builder = DetailBuilder(
            self.game,
            x=self.star.x,
            y=self.star.y,
            player=self.player
        )
        detail = builder.build_detail()

        self.assertEqual(detail['report_year'], 2400)
        self.assertFalse(detail['is_current'])
        self.assertEqual(detail['name'], 'Old Name')
        self.assertEqual(detail['population'], 1000)

    def test_cached_report_includes_capacity(self):
        """Cached star reports should include and display capacity."""
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=2400,
            target_type='star',
            target_id=self.star.id,
            cached_report='{"name": "Old Name", "colonists": 1000, '
                         '"capacity": 123456, '
                         '"gravity": 1.0, "temperature": 1.0, "radiation": 1.0}'
        )

        builder = DetailBuilder(
            self.game,
            x=self.star.x,
            y=self.star.y,
            player=self.player
        )
        detail = builder.build_detail()

        self.assertFalse(detail['is_current'])
        self.assertEqual(detail['capacity'], 123456)

    def test_cached_report_includes_survivability_flag(self):
        """Cached star reports should preserve survivability status."""
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=2400,
            target_type='star',
            target_id=self.star.id,
            cached_report='{"name": "Old Name", "colonists": 1000, '
                         '"is_survivable": false, '
                         '"gravity": 1.0, "temperature": 1.0, "radiation": 1.0}'
        )

        builder = DetailBuilder(
            self.game,
            x=self.star.x,
            y=self.star.y,
            player=self.player
        )
        detail = builder.build_detail()

        self.assertFalse(detail['is_current'])
        self.assertFalse(detail['is_survivable'])

    def test_basic_cached_report_derives_habitability_summary(self):
        """Basic cached reports still show survivability and population cap."""
        self.star.base_capacity = 45
        self.star.save(update_fields=['base_capacity'])
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=2400,
            target_type='star',
            target_id=self.star.id,
            cached_report='{"name": "Old Name", '
                         '"report_tier": "basic", '
                         '"gravity": 1.0, '
                         '"temperature": 1.0, '
                         '"radiation": 1.0}'
        )

        builder = DetailBuilder(
            self.game,
            x=self.star.x,
            y=self.star.y,
            player=self.player
        )
        detail = builder.build_detail()

        self.assertEqual(detail['report_tier'], 'basic')
        self.assertTrue(detail['is_survivable'])
        self.assertEqual(detail['capacity'], 45000000)

    def test_report_age_calculated_correctly(self):
        """Report age shows years since report was generated."""
        # Game starts at year 2400, advance to 2405
        self.game.year = 2405
        self.game.save()

        Report.objects.create(
            game=self.game,
            player=self.player,
            year=2402,  # Report from 3 years ago
            target_type='star',
            target_id=self.star.id,
            cached_report='{"name": "Test", "colonists": 100, '
                         '"gravity": 1.0, "temperature": 1.0, "radiation": 1.0}'
        )

        builder = DetailBuilder(
            self.game,
            x=self.star.x,
            y=self.star.y,
            player=self.player
        )
        detail = builder.build_detail()

        self.assertEqual(detail['report_year'], 2402)
        self.assertEqual(detail['report_age'], 3)  # 2405 - 2402 = 3 years old

    def test_current_view_shows_live_data(self):
        """When viewing with fleet present, shows current data."""
        Report.objects.create(
            game=self.game,
            player=self.player,
            year=2400,
            target_type='star',
            target_id=self.star.id,
            cached_report='{"name": "Old Name", "colonists": 1000}'
        )

        Fleet.objects.create(
            game=self.game,
            player=self.player,
            name='Scout',
            x=self.star.x,
            y=self.star.y
        )

        self.star.name = 'Current Name'
        self.star.colonists = 5000
        self.star.save()

        builder = DetailBuilder(
            self.game,
            x=self.star.x,
            y=self.star.y,
            player=self.player
        )
        detail = builder.build_detail()

        self.assertIsNone(detail['report_year'])
        self.assertTrue(detail['is_current'])
        self.assertEqual(detail['name'], 'Current Name')
        self.assertEqual(detail['population'], 5000)


class ScannerReportTest(TestCase):
    def setUp(self):
        get_default_race_type()
        self.user1 = User.objects.create_user('scanner_p1', 'sp1@test.com', 'pass')
        self.account1 = Account.objects.create(django_user=self.user1)
        self.user2 = User.objects.create_user('scanner_p2', 'sp2@test.com', 'pass')
        self.account2 = Account.objects.create(django_user=self.user2)

        factory = GameFactory()
        factory.set_map_size(100, 100)
        factory.set_owner(self.account1)
        factory.create_stars(12)
        self.game = factory.save()
        self.game.joinable = True
        self.game.save(update_fields=['joinable'])
        self.player1 = factory.join_player(self.account1, get_default_race())
        self.player2 = factory.join_player(self.account2, get_default_race())

        self.enemy_star = self.player2.homeworld

    def _find_empty_coord(self, exclude_star=None):
        occupied = set(
            self.game.stars.exclude(id=getattr(exclude_star, 'id', None)).values_list('x', 'y')
        )
        for x in range(1, int(self.game.map_size_x)):
            for y in range(1, int(self.game.map_size_y)):
                if (x, y) not in occupied:
                    return x, y
        return None, None

    def _place_enemy_star_near(self, x, y, distance=4):
        occupied = set(
            self.game.stars.exclude(id=self.enemy_star.id).values_list('x', 'y')
        )
        max_x = int(self.game.map_size_x)
        max_y = int(self.game.map_size_y)

        def in_bounds(cx, cy):
            return 1 <= int(cx) < max_x and 1 <= int(cy) < max_y

        def first_open(candidates):
            for cx, cy in candidates:
                if not in_bounds(cx, cy):
                    continue
                if (int(cx), int(cy)) in occupied:
                    continue
                return int(cx), int(cy)
            return None, None

        cardinal = [
            (x + distance, y),
            (x - distance, y),
            (x, y + distance),
            (x, y - distance),
        ]
        tx, ty = first_open(cardinal)

        if tx is None or ty is None:
            nearby = []
            for dx in range(-distance, distance + 1):
                for dy in range(-distance, distance + 1):
                    if dx == 0 and dy == 0:
                        continue
                    if (dx * dx) + (dy * dy) > (distance * distance):
                        continue
                    nearby.append((x + dx, y + dy))
            tx, ty = first_open(nearby)

        if tx is None or ty is None:
            tx, ty = self._find_empty_coord(exclude_star=self.enemy_star)
        self.enemy_star.x = tx
        self.enemy_star.y = ty
        self.enemy_star.save(update_fields=['x', 'y'])
        return self.enemy_star

    def _create_scanner_fleet(self, basic, advanced, x=10, y=10):
        return Fleet.objects.create(
            game=self.game,
            player=self.player1,
            name='Scanner Fleet',
            x=x,
            y=y,
            basic_scanner_range=basic,
            advanced_scanner_range=advanced,
        )

    def test_basic_scanner_reports_star_habitability_summary_only(self):
        fleet = self._create_scanner_fleet(basic=6, advanced=0, x=10, y=10)
        star = self._place_enemy_star_near(fleet.x, fleet.y, distance=4)

        GameTurn(self.game).generate_scanner_reports()
        report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='star',
            target_id=star.id,
        )
        data = report.get_report_data()
        self.assertEqual(data.get('report_tier'), 'basic')
        self.assertIn('gravity', data)
        self.assertIn('temperature', data)
        self.assertIn('radiation', data)
        self.assertIn('capacity', data)
        self.assertIn('is_survivable', data)
        self.assertNotIn('ironium_yield', data)
        self.assertNotIn('player_name', data)
        self.assertNotIn('colonists', data)

    def test_basic_scanner_rolls_up_habitable_star_messages(self):
        fleet = self._create_scanner_fleet(basic=8, advanced=0, x=10, y=10)
        first_star = self._place_enemy_star_near(fleet.x, fleet.y, distance=4)
        second_star = self.game.stars.filter(
            player__isnull=True
        ).exclude(id=first_star.id).first()

        first_star.gravity = self.player1.gravity_center
        first_star.temperature = self.player1.temperature_center
        first_star.radiation = self.player1.radiation_center
        first_star.save(update_fields=['gravity', 'temperature', 'radiation'])

        second_star.x = fleet.x
        second_star.y = fleet.y + 5
        second_star.gravity = self.player1.gravity_center
        second_star.temperature = self.player1.temperature_center
        second_star.radiation = self.player1.radiation_center
        second_star.save(update_fields=[
            'x', 'y', 'gravity', 'temperature', 'radiation'
        ])

        turn = GameTurn(self.game)
        turn.generate_scanner_reports()
        turn.generate_scanner_reports()

        messages = GameMessage.objects.filter(
            game=self.game,
            player=self.player1,
            category='ENVIRONMENTAL',
        )
        self.assertEqual(messages.count(), 1)
        message = messages.first()
        self.assertIn('potentially habitable stars', message.message)
        self.assertIn(first_star.name, message.message)
        self.assertIn(second_star.name, message.message)

    def test_advanced_scanner_reports_star_minerals_no_infrastructure(self):
        fleet = self._create_scanner_fleet(basic=6, advanced=6, x=12, y=12)
        star = self._place_enemy_star_near(fleet.x, fleet.y, distance=4)

        GameTurn(self.game).generate_scanner_reports()
        report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='star',
            target_id=star.id,
        )
        data = report.get_report_data()
        self.assertEqual(data.get('report_tier'), 'advanced')
        self.assertIn('ironium_yield', data)
        self.assertIn('ironium_inventory', data)
        self.assertIn('player_name', data)
        self.assertIn('colonists', data)
        self.assertNotIn('mines', data)
        self.assertNotIn('factories', data)

    def test_advanced_scanner_refreshes_stale_encounter_star_ownership(self):
        fleet = self._create_scanner_fleet(basic=6, advanced=6, x=12, y=12)
        star = self._place_enemy_star_near(fleet.x, fleet.y, distance=4)
        star.player = None
        star.colonists = 0
        star.save(update_fields=['player', 'colonists'])

        report = Report.objects.create(
            game=self.game,
            player=self.player1,
            year=self.game.year - 71,
            target_type='star',
            target_id=star.id,
            cached_report=json.dumps({
                'name': star.name,
                'x': star.x,
                'y': star.y,
                'gravity': star.gravity,
                'temperature': star.temperature,
                'radiation': star.radiation,
                'player_name': None,
                'colonists': 0,
                'mines': 5,
                'factories': 3,
                'report_tier': 'encounter',
            }),
        )

        star.player = self.player2
        star.colonists = 42000
        star.save(update_fields=['player', 'colonists'])

        GameTurn(self.game).generate_scanner_reports()
        report.refresh_from_db()
        data = report.get_report_data()
        self.assertEqual(report.year, self.game.year)
        self.assertEqual(data.get('report_tier'), 'encounter')
        self.assertEqual(data.get('player_name'), self.player2.name)
        self.assertEqual(data.get('colonists'), 42000)
        self.assertEqual(data.get('mines'), 5)
        self.assertEqual(data.get('factories'), 3)

    def test_basic_scanner_reports_fleet_presence_only(self):
        fleet = self._create_scanner_fleet(basic=6, advanced=0, x=10, y=10)
        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Enemy Scout',
            x=fleet.x + 3,
            y=fleet.y,
            ship_count=4,
            integrity=77,
            heading=123.4,
            travel_warp=6,
            warp_advantage=0.9,
        )

        GameTurn(self.game).generate_scanner_reports()
        report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='fleet',
            target_id=enemy_fleet.id,
        )
        data = report.get_report_data()
        self.assertEqual(data.get('report_tier'), 'basic')
        self.assertEqual(data.get('name'), format_basic_unknown_fleet_name(enemy_fleet))
        self.assertNotEqual(data.get('name'), enemy_fleet.name)
        self.assertEqual(data.get('travel_warp'), 6)
        self.assertAlmostEqual(float(data.get('warp_advantage')), 0.9, places=2)
        self.assertAlmostEqual(float(data.get('heading')), 123.4, places=1)
        self.assertNotIn('ship_count', data)
        self.assertNotIn('integrity', data)

        enemy_fleet.name = 'Renamed Leak Attempt'
        enemy_fleet.save(update_fields=['name'])
        GameTurn(self.game).generate_scanner_reports()
        report.refresh_from_db()
        self.assertEqual(
            report.get_report_data().get('name'),
            format_basic_unknown_fleet_name(enemy_fleet)
        )

    def test_visible_fleet_uses_live_motion_over_stale_report_motion(self):
        scanner = self._create_scanner_fleet(basic=8, advanced=0, x=10, y=10)
        star = self._place_enemy_star_near(scanner.x, scanner.y, distance=4)
        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Archive Raider',
            x=star.x,
            y=star.y,
            ship_count=3,
            integrity=88,
            heading=151.3,
            travel_warp=0,
        )
        report = Report.objects.create(
            game=self.game,
            player=self.player1,
            year=self.game.year - 5,
            target_type='fleet',
            target_id=enemy_fleet.id,
            cached_report='{}',
        )
        report.set_report_data({
            'name': enemy_fleet.name,
            'x': star.x + 7,
            'y': star.y + 7,
            'report_tier': 'encounter',
            'player_name': self.player2.name,
            'ship_count': 3,
            'integrity': 88,
            'travel_warp': 9,
            'heading': 44.0,
        })
        report.save(update_fields=['cached_report'])

        detail = DetailBuilder(
            self.game,
            selected=enemy_fleet.short_id,
            player=self.player1,
        ).build_detail()

        self.assertEqual(detail.get('report_tier'), 'encounter')
        self.assertEqual(detail.get('travel_warp'), 0)
        self.assertAlmostEqual(float(detail.get('heading')), 151.3, places=1)
        self.assertEqual(detail.get('x'), enemy_fleet.x)
        self.assertEqual(detail.get('y'), enemy_fleet.y)
        self.assertEqual(detail.get('fleet_motion_summary'), 'In orbit')

    def test_advanced_scanner_reports_fleet_composition_only(self):
        fleet = self._create_scanner_fleet(basic=6, advanced=6, x=15, y=15)
        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Enemy Hauler',
            x=fleet.x + 3,
            y=fleet.y,
            ship_count=6,
            integrity=55,
            cargo_capacity=300,
            ironium_inventory=90,
            boranium_inventory=40,
            germanium_inventory=20,
            colonists=10,
            max_safe_warp=9,
            has_bombs='CONVENTIONAL',
        )

        GameTurn(self.game).generate_scanner_reports()
        report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='fleet',
            target_id=enemy_fleet.id,
        )
        data = report.get_report_data()
        self.assertEqual(data.get('report_tier'), 'advanced')
        self.assertEqual(data.get('ship_count'), 6)
        self.assertEqual(data.get('integrity'), 55)
        self.assertNotIn('ironium_inventory', data)
        self.assertNotIn('cargo_capacity', data)
        self.assertNotIn('max_safe_warp', data)
        self.assertNotIn('has_bombs', data)
        self.assertNotIn('offense_modifier', data)

    def test_allied_scanner_sharing_generates_reports_for_recipient(self):
        scanner = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Shared Scanner',
            x=70,
            y=70,
            basic_scanner_range=6,
            advanced_scanner_range=0,
        )
        star = self.game.stars.exclude(player=self.player1).exclude(player=self.player2).first()
        if star is None:
            star = self.game.stars.exclude(id=self.player1.homeworld_id).first()
        star.x = scanner.x + 4
        star.y = scanner.y
        star.save(update_fields=['x', 'y'])

        PlayerDiplomaticStance.objects.create(
            player=self.player2,
            target_player=self.player1,
            stance='ALLIED',
        )

        GameTurn(self.game).generate_scanner_reports()

        report = Report.objects.filter(
            game=self.game,
            player=self.player1,
            target_type='star',
            target_id=star.id,
        ).first()
        self.assertIsNotNone(report)
        self.assertEqual(report.get_report_data().get('report_tier'), 'basic')

    def test_allied_intel_sharing_creates_advanced_fleet_and_colony_reports(self):
        shared_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Shared Intel Fleet',
            x=61,
            y=62,
            ship_count=3,
            integrity=77,
        )
        shared_star = self.player2.homeworld

        PlayerDiplomaticStance.objects.create(
            player=self.player2,
            target_player=self.player1,
            stance='ALLIED',
        )

        turn = GameTurn(self.game)
        turn.generate_shared_intel_reports()

        fleet_report = Report.objects.filter(
            game=self.game,
            player=self.player1,
            target_type='fleet',
            target_id=shared_fleet.id,
        ).first()
        self.assertIsNotNone(fleet_report)
        self.assertEqual(fleet_report.get_report_data().get('report_tier'), 'advanced')
        self.assertEqual(fleet_report.get_report_data().get('player_name'), self.player2.name)

        star_report = Report.objects.filter(
            game=self.game,
            player=self.player1,
            target_type='star',
            target_id=shared_star.id,
        ).first()
        self.assertIsNotNone(star_report)
        self.assertEqual(star_report.get_report_data().get('report_tier'), 'advanced')
        self.assertEqual(star_report.get_report_data().get('player_name'), self.player2.name)

    def test_advanced_scanner_reports_salvage_and_anomaly(self):
        fleet = self._create_scanner_fleet(basic=6, advanced=6, x=20, y=20)
        salvage = Salvage.objects.create(
            game=self.game,
            x=fleet.x + 2,
            y=fleet.y,
            salvage_type=Salvage.TYPE_ANCIENT_DEBRIS,
            ironium_inventory=10,
            boranium_inventory=5,
            germanium_inventory=2,
        )
        anomaly = Anomaly.objects.create(
            game=self.game,
            x=fleet.x + 3,
            y=fleet.y,
            name='Scanner Rift',
            anomaly_type=Anomaly.TYPE_RIFT,
        )

        GameTurn(self.game).generate_scanner_reports()
        salvage_report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='salvage',
            target_id=salvage.id,
        )
        anomaly_report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='anomaly',
            target_id=anomaly.id,
        )
        self.assertEqual(salvage_report.get_report_data().get('report_tier'), 'advanced')
        self.assertEqual(
            salvage_report.get_report_data().get('salvage_type'),
            Salvage.TYPE_ANCIENT_DEBRIS,
        )
        self.assertEqual(anomaly_report.get_report_data().get('report_tier'), 'advanced')

    def test_basic_scanner_reports_ancient_debris_total_without_type_and_anomaly_type(self):
        fleet = self._create_scanner_fleet(basic=6, advanced=0, x=20, y=20)
        salvage = Salvage.objects.create(
            game=self.game,
            x=fleet.x + 2,
            y=fleet.y,
            salvage_type=Salvage.TYPE_ANCIENT_DEBRIS,
            ironium_inventory=10,
            boranium_inventory=5,
            germanium_inventory=2,
        )
        anomaly = Anomaly.objects.create(
            game=self.game,
            x=fleet.x + 3,
            y=fleet.y,
            name='Scanner Rift',
            anomaly_type=Anomaly.TYPE_RIFT,
            stability=77,
        )

        GameTurn(self.game).generate_scanner_reports()
        salvage_report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='salvage',
            target_id=salvage.id,
        )
        anomaly_report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='anomaly',
            target_id=anomaly.id,
        )

        salvage_data = salvage_report.get_report_data()
        anomaly_data = anomaly_report.get_report_data()
        self.assertEqual(salvage_data.get('report_tier'), 'basic')
        self.assertEqual(
            salvage_data.get('name'),
            format_basic_hidden_salvage_name(salvage)
        )
        self.assertIsNone(salvage_data.get('salvage_type'))
        self.assertEqual(salvage_data.get('total_minerals'), salvage.total_minerals)
        self.assertNotIn('ironium_inventory', salvage_data)
        self.assertEqual(anomaly_data.get('report_tier'), 'basic')
        self.assertEqual(anomaly_data.get('anomaly_type'), Anomaly.TYPE_RIFT)
        self.assertNotIn('stability', anomaly_data)

    def test_encounter_reports_include_infrastructure_and_capabilities(self):
        x, y = self._find_empty_coord(exclude_star=self.enemy_star)
        self.enemy_star.x = x
        self.enemy_star.y = y
        self.enemy_star.mines = 4
        self.enemy_star.factories = 3
        self.enemy_star.labs = 2
        self.enemy_star.defenses = 1
        self.enemy_star.shipyards = 1
        self.enemy_star.save()

        Fleet.objects.create(
            game=self.game,
            player=self.player1,
            name='Encounter Fleet',
            x=x,
            y=y,
            advanced_scanner_range=6,
        )
        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Enemy Combat',
            x=x,
            y=y,
            ship_count=5,
            integrity=88,
            max_safe_warp=7,
            has_bombs='CONVENTIONAL',
            has_miners='SMALL',
            has_wormhole_drive=True,
        )
        salvage = Salvage.objects.create(
            game=self.game,
            x=x,
            y=y,
            ironium_inventory=11,
            boranium_inventory=7,
            germanium_inventory=3,
        )
        anomaly = Anomaly.objects.create(
            game=self.game,
            x=x,
            y=y,
            name='Encounter Nebula',
            anomaly_type=Anomaly.TYPE_NEBULA,
        )

        GameTurn(self.game).generate_reports()

        star_report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='star',
            target_id=self.enemy_star.id,
        )
        star_data = star_report.get_report_data()
        self.assertEqual(star_data.get('report_tier'), 'encounter')
        self.assertEqual(star_data.get('mines'), 4)
        self.assertEqual(star_data.get('factories'), 3)
        self.assertEqual(star_data.get('labs'), 2)
        self.assertEqual(star_data.get('defenses'), 1)
        self.assertEqual(star_data.get('shipyards'), 1)

        fleet_report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='fleet',
            target_id=enemy_fleet.id,
        )
        fleet_data = fleet_report.get_report_data()
        self.assertEqual(fleet_data.get('report_tier'), 'encounter')
        self.assertEqual(fleet_data.get('max_safe_warp'), 7)
        self.assertEqual(fleet_data.get('has_bombs'), 'CONVENTIONAL')
        self.assertEqual(fleet_data.get('has_miners'), 'SMALL')
        self.assertTrue(fleet_data.get('has_wormhole_drive'))

        salvage_report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='salvage',
            target_id=salvage.id,
        )
        self.assertEqual(salvage_report.get_report_data().get('report_tier'), 'encounter')

        anomaly_report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='anomaly',
            target_id=anomaly.id,
        )
        self.assertEqual(anomaly_report.get_report_data().get('report_tier'), 'encounter')

    def test_encounter_without_advanced_scanners_hides_fleet_cargo(self):
        x, y = self._find_empty_coord(exclude_star=self.enemy_star)
        Fleet.objects.create(
            game=self.game,
            player=self.player1,
            name='No Advanced',
            x=x,
            y=y,
            advanced_scanner_range=0,
        )
        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Enemy Cargo',
            x=x,
            y=y,
            ship_count=3,
            integrity=70,
            cargo_capacity=200,
            ironium_inventory=55,
        )

        GameTurn(self.game).generate_reports()
        report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='fleet',
            target_id=enemy_fleet.id,
        )
        data = report.get_report_data()
        self.assertEqual(data.get('report_tier'), 'encounter')
        self.assertNotIn('ironium_inventory', data)
        self.assertNotIn('cargo_capacity', data)
        self.assertNotIn('max_safe_warp', data)
        self.assertNotIn('offense_modifier', data)
        self.assertNotIn('has_bombs', data)
        self.assertNotIn('basic_scanner_range', data)

    def test_encounter_with_advanced_scanners_shows_fleet_cargo(self):
        x, y = self._find_empty_coord(exclude_star=self.enemy_star)
        Fleet.objects.create(
            game=self.game,
            player=self.player1,
            name='Advanced Scout',
            x=x,
            y=y,
            advanced_scanner_range=6,
        )
        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Enemy Cargo',
            x=x,
            y=y,
            ship_count=4,
            integrity=90,
            cargo_capacity=220,
            ironium_inventory=60,
        )

        GameTurn(self.game).generate_reports()
        report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='fleet',
            target_id=enemy_fleet.id,
        )
        data = report.get_report_data()
        self.assertEqual(data.get('report_tier'), 'encounter')
        self.assertEqual(data.get('ironium_inventory'), 60)
        self.assertEqual(data.get('cargo_capacity'), 220)


class NoScannerReportTierTest(TestCase):
    def setUp(self):
        get_default_race_type()
        self.user1 = User.objects.create_user('noscan_p1', 'nsp1@test.com', 'pass')
        self.account1 = Account.objects.create(django_user=self.user1)
        self.user2 = User.objects.create_user('noscan_p2', 'nsp2@test.com', 'pass')
        self.account2 = Account.objects.create(django_user=self.user2)

        factory = GameFactory()
        factory.set_map_size(100, 100)
        factory.set_owner(self.account1)
        factory.create_stars(10)
        self.game = factory.save()
        self.game.joinable = True
        self.game.no_scanners = True
        self.game.save(update_fields=['joinable', 'no_scanners'])
        self.player1 = factory.join_player(self.account1, get_default_race())
        self.player2 = factory.join_player(self.account2, get_default_race())
        self.enemy_star = self.player2.homeworld

    def _visit_enemy_star(self, basic, advanced):
        fleet = Fleet.objects.create(
            game=self.game,
            player=self.player1,
            name='Visit Fleet',
            x=self.enemy_star.x,
            y=self.enemy_star.y,
            basic_scanner_range=basic,
            advanced_scanner_range=advanced,
        )
        GameTurn(self.game).generate_reports()
        report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='star',
            target_id=self.enemy_star.id,
        )
        return report.get_report_data()

    def test_visit_without_scanners_only_reports_ownership(self):
        data = self._visit_enemy_star(basic=0, advanced=0)
        self.assertEqual(data.get('report_tier'), 'ownership')
        self.assertNotIn('gravity', data)
        self.assertIn('player_name', data)

    def test_no_scanners_ownership_fleet_report_includes_heading_and_travel_warp(self):
        x = self.enemy_star.x
        y = self.enemy_star.y
        Fleet.objects.create(
            game=self.game,
            player=self.player1,
            name='Blind Watcher',
            x=x,
            y=y,
            basic_scanner_range=0,
            advanced_scanner_range=0,
        )
        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Vector Ghost',
            x=x,
            y=y,
            ship_count=2,
            heading=278.3,
            travel_warp=6,
        )

        GameTurn(self.game).generate_reports()
        data = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='fleet',
            target_id=enemy_fleet.id,
        ).get_report_data()

        self.assertEqual(data.get('report_tier'), 'ownership')
        self.assertIn('player_name', data)
        self.assertEqual(data.get('travel_warp'), 6)
        self.assertAlmostEqual(float(data.get('heading')), 278.3, places=1)

    def test_visit_with_basic_scanners_reports_environment_only(self):
        data = self._visit_enemy_star(basic=5, advanced=0)
        self.assertEqual(data.get('report_tier'), 'basic')
        self.assertIn('gravity', data)
        self.assertIn('capacity', data)
        self.assertIn('is_survivable', data)
        self.assertNotIn('ironium_yield', data)

    def test_visit_with_advanced_scanners_reports_resources(self):
        data = self._visit_enemy_star(basic=5, advanced=10)
        self.assertEqual(data.get('report_tier'), 'advanced')
        self.assertIn('ironium_yield', data)
        self.assertNotIn('mines', data)

    def test_visit_with_high_advanced_scanners_reports_encounter(self):
        self.enemy_star.mines = 3
        self.enemy_star.factories = 2
        self.enemy_star.save(update_fields=['mines', 'factories'])
        data = self._visit_enemy_star(basic=5, advanced=25)
        self.assertEqual(data.get('report_tier'), 'encounter')
        self.assertEqual(data.get('mines'), 3)
        self.assertEqual(data.get('factories'), 2)

    def test_no_scanners_disables_range_reports(self):
        Fleet.objects.create(
            game=self.game,
            player=self.player1,
            name='Scanner',
            x=10,
            y=10,
            basic_scanner_range=20,
            advanced_scanner_range=20,
        )
        self.enemy_star.x = 12
        self.enemy_star.y = 10
        self.enemy_star.save(update_fields=['x', 'y'])

        GameTurn(self.game).generate_scanner_reports()
        self.assertFalse(Report.objects.filter(
            game=self.game,
            player=self.player1,
            target_type='star',
            target_id=self.enemy_star.id,
        ).exists())

    def test_no_scanners_high_advanced_requires_visit_for_encounter(self):
        Fleet.objects.create(
            game=self.game,
            player=self.player1,
            name='Long Range',
            x=10,
            y=10,
            basic_scanner_range=0,
            advanced_scanner_range=25,
        )
        self.enemy_star.x = 13
        self.enemy_star.y = 10
        self.enemy_star.save(update_fields=['x', 'y'])

        GameTurn(self.game).generate_scanner_reports()
        self.assertFalse(Report.objects.filter(
            game=self.game,
            player=self.player1,
            target_type='star',
            target_id=self.enemy_star.id,
        ).exists())

    def test_no_scanners_basic_visit_hides_fleet_capabilities_without_advanced(self):
        x = self.enemy_star.x
        y = self.enemy_star.y
        Fleet.objects.create(
            game=self.game,
            player=self.player1,
            name='Visitor',
            x=x,
            y=y,
            basic_scanner_range=5,
            advanced_scanner_range=0,
        )
        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Enemy Fleet',
            x=x,
            y=y,
            ship_count=4,
            integrity=90,
            max_safe_warp=9,
            has_bombs='CONVENTIONAL',
        )

        GameTurn(self.game).generate_reports()

        data = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='fleet',
            target_id=enemy_fleet.id,
        ).get_report_data()
        self.assertEqual(data.get('report_tier'), 'basic')
        self.assertNotIn('max_safe_warp', data)
        self.assertNotIn('offense_modifier', data)
        self.assertNotIn('has_bombs', data)

    def test_no_scanners_basic_fleet_report_keeps_identity_after_contact(self):
        x = self.enemy_star.x
        y = self.enemy_star.y
        own_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player1,
            name='Contact Fleet',
            x=x,
            y=y,
            basic_scanner_range=5,
            advanced_scanner_range=0,
        )
        enemy_fleet = Fleet.objects.create(
            game=self.game,
            player=self.player2,
            name='Vector Ghost',
            x=x,
            y=y,
            ship_count=4,
            integrity=90,
        )

        turn = GameTurn(self.game)
        turn.first_contact_checks()
        turn.generate_reports()

        report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='fleet',
            target_id=enemy_fleet.id,
        )
        self.assertEqual(report.get_report_data().get('report_tier'), 'basic')
        self.assertIsNone(report.get_report_data().get('player_name'))

        own_fleet.delete()

        detail = DetailBuilder(
            self.game,
            x=x,
            y=y,
            selected=enemy_fleet.short_id,
            player=self.player1,
        ).build_detail()

        self.assertEqual(detail.get('report_tier'), 'basic')
        self.assertEqual(detail.get('name'), 'Vector Ghost')
        self.assertEqual(
            detail.get('player'),
            '%s (%s)' % (self.player2.name, self.player2.account.alias),
        )
        self.assertTrue(detail.get('owner_known'))

    def test_no_scanners_basic_visit_records_anomaly_type(self):
        anomaly = Anomaly.objects.create(
            game=self.game,
            x=10,
            y=12,
            name='Basic Anomaly',
            anomaly_type=Anomaly.TYPE_BLACK_HOLE,
        )
        Fleet.objects.create(
            game=self.game,
            player=self.player1,
            name='Basic Visit',
            x=anomaly.x,
            y=anomaly.y,
            basic_scanner_range=5,
            advanced_scanner_range=0,
        )
        GameTurn(self.game).generate_reports()
        report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='anomaly',
            target_id=anomaly.id,
        )
        data = report.get_report_data()
        self.assertEqual(data.get('report_tier'), 'basic')
        self.assertEqual(data.get('anomaly_type'), Anomaly.TYPE_BLACK_HOLE)
        self.assertNotIn('stability', data)

    def test_no_scanners_basic_visit_reveals_salvage_inventory(self):
        salvage = Salvage.objects.create(
            game=self.game,
            x=14,
            y=16,
            ironium_inventory=40,
            boranium_inventory=30,
            germanium_inventory=20,
            resource_x_inventory=10,
            salvage_type=Salvage.TYPE_SALVAGE,
        )
        Fleet.objects.create(
            game=self.game,
            player=self.player1,
            name='Basic Salvage Visit',
            x=salvage.x,
            y=salvage.y,
            basic_scanner_range=5,
            advanced_scanner_range=0,
        )

        GameTurn(self.game).generate_reports()

        report = Report.objects.get(
            game=self.game,
            player=self.player1,
            target_type='salvage',
            target_id=salvage.id,
        )
        data = report.get_report_data()

        self.assertEqual(data.get('report_tier'), 'basic')
        self.assertEqual(data.get('salvage_type'), Salvage.TYPE_SALVAGE)
        self.assertEqual(data.get('total_minerals'), salvage.total_minerals)
        self.assertEqual(data.get('ironium_inventory'), 40)
        self.assertEqual(data.get('boranium_inventory'), 30)
        self.assertEqual(data.get('germanium_inventory'), 20)
        self.assertEqual(data.get('resource_x_inventory'), 10)

    def test_no_scanners_high_advanced_visit_reports_star_encounter(self):
        Fleet.objects.create(
            game=self.game,
            player=self.player1,
            name='Visitor',
            x=self.enemy_star.x,
            y=self.enemy_star.y,
            basic_scanner_range=0,
            advanced_scanner_range=25,
        )
        GameTurn(self.game).generate_reports()
        report = Report.objects.filter(
            game=self.game,
            player=self.player1,
            target_type='star',
            target_id=self.enemy_star.id,
        ).first()
        self.assertIsNotNone(report)
        self.assertEqual(report.get_report_data().get('report_tier'), 'encounter')


class ReportTierMergeTest(TestCase):
    def setUp(self):
        self.game = default_game(stars=5, fleets=0)
        self.player = self.game.players.first()
        self.star = self.game.stars.filter(player__isnull=True).first()

    def test_encounter_report_is_not_downgraded(self):
        report = Report.objects.create(
            game=self.game,
            player=self.player,
            year=self.game.year,
            target_type='star',
            target_id=self.star.id,
            cached_report=json.dumps({
                'name': self.star.name,
                'x': self.star.x,
                'y': self.star.y,
                'report_tier': 'encounter',
            }),
        )
        turn = GameTurn(self.game)
        turn._create_or_update_report(
            self.player, 'star', self.star, self.game.year + 1, report_tier='basic'
        )
        report.refresh_from_db()
        self.assertEqual(report.get_report_data().get('report_tier'), 'encounter')
