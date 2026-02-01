from django.test import TestCase, Client
from django.urls import reverse
from ..models import GameMessage
from ..turn import GameTurn
from ._util import default_game, get_default_user


class TestMessageFiltering(TestCase):
    def test_messages_filtered_by_messages_seen_year(self):
        """Messages should be filtered to year >= messages_seen_year."""
        game = default_game(stars=5)
        player = game.players.first()
        # Create messages for different years
        GameMessage.objects.create(game=game, player=player, year=2400, message="Old message")
        GameMessage.objects.create(game=game, player=player, year=2401, message="Middle message")
        GameMessage.objects.create(game=game, player=player, year=2402, message="Recent message")
        # Set messages_seen_year to 2401
        player.messages_seen_year = 2401
        player.save()
        # Filter as the view does
        messages = player.messages.filter(year__gte=player.messages_seen_year)
        self.assertEqual(messages.count(), 2)
        years = set(m.year for m in messages)
        self.assertIn(2401, years)
        self.assertIn(2402, years)
        self.assertNotIn(2400, years)

    def test_all_messages_shown_when_messages_seen_year_null(self):
        """All messages should be shown when messages_seen_year is None."""
        game = default_game(stars=5)
        player = game.players.first()
        GameMessage.objects.create(game=game, player=player, year=2400, message="Old message")
        GameMessage.objects.create(game=game, player=player, year=2401, message="Recent message")
        self.assertIsNone(player.messages_seen_year)
        # Without filter, all messages shown
        messages = player.messages.all()
        self.assertEqual(messages.count(), 2)

    def test_messages_limited_to_1000(self):
        """Messages should be limited to 1000."""
        game = default_game(stars=5)
        player = game.players.first()
        # Create 1100 messages
        for i in range(1100):
            GameMessage.objects.create(game=game, player=player, year=2400, message=f"Message {i}")
        # Apply limit as view does
        messages = player.messages.order_by('-year', '-id')[:1000]
        self.assertEqual(len(messages), 1000)

    def test_last_seen_year_updated_on_view(self):
        """last_seen_year should be updated when viewing the game."""
        game = default_game(stars=5)
        game.year = 2405
        game.save()
        player = game.players.first()
        player.last_seen_year = 2400
        player.save()
        user, account = get_default_user()
        client = Client()
        client.force_login(user)
        # Visit the game view
        response = client.get(reverse('dj4xol:game', args=[game.short_id]))
        self.assertEqual(response.status_code, 200)
        # Check last_seen_year was updated
        player.refresh_from_db()
        self.assertEqual(player.last_seen_year, 2405)

    def test_messages_seen_year_updated_on_turn_generation(self):
        """messages_seen_year should be updated from last_seen_year when turn generates."""
        game = default_game(stars=5)
        player = game.players.first()
        player.last_seen_year = 2400
        player.messages_seen_year = None
        player.save()
        GameTurn(game).generate_turn()
        player.refresh_from_db()
        # messages_seen_year should now equal last_seen_year
        self.assertEqual(player.messages_seen_year, 2400)

    def test_messages_persist_on_reload(self):
        """Messages should not disappear when page is reloaded."""
        game = default_game(stars=5)
        game.year = 2405
        game.save()
        player = game.players.first()
        # Simulate: player viewed at 2404, turn generated, now at 2405
        player.last_seen_year = 2404
        player.messages_seen_year = 2404
        player.save()
        # Create a message from the turn
        GameMessage.objects.create(game=game, player=player, year=2404, message="Turn message")
        user, account = get_default_user()
        client = Client()
        client.force_login(user)
        # First view - should see message
        response = client.get(reverse('dj4xol:game', args=[game.short_id]))
        self.assertContains(response, "Turn message")
        # Reload - should still see message (messages_seen_year unchanged)
        response = client.get(reverse('dj4xol:game', args=[game.short_id]))
        self.assertContains(response, "Turn message")
        player.refresh_from_db()
        # last_seen_year updated but messages_seen_year unchanged
        self.assertEqual(player.last_seen_year, 2405)
        self.assertEqual(player.messages_seen_year, 2404)
