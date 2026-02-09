"""Tests for the exploration reports feature."""
from django.test import TestCase
from django.contrib.auth.models import User
from ..models import (
    Account, Star, Fleet, Salvage, Report
)
from ..factory import GameFactory
from ..objectdetails import DetailBuilder
from ..turn import GameTurn
from ._util import get_default_race_type, get_default_race


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
        self.star1.gravity = 1.5
        self.star1.temperature = 0.8
        self.star1.radiation = 1.2
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
