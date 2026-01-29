from ..factory import GameFactory
from ..models import Game, Player
from django.contrib.auth.models import User


def get_default_user():
    """Retrieve or create a default user for testing purposes."""
    django_user = User.objects.first()
    if not django_user:
        django_user = User.objects.create_user(
            username="default_user", email="            username="default_user", email="test@xyz.com", password="1234")
    player, _ = Player.objects.get_or_create(django_user=django_user)
    return django_user, player


def empty_game():
    """Create an empty game instance for testing purposes."""
    user, player = get_default_user()
    factory = GameFactory()
    factory.new()
    factory.set_map_size(100, 100)
    factory.set_owner(player)
    return factory.save()


def default_game_factory(size_x=100, size_y=100, stars=50, ships=3):
    """Create a default game instance for testing purposes."""
    user, player = get_default_user()
    factory = GameFactory()
    factory.new()
    factory.set_map_size(size_x, size_y)
    factory.set_owner(player)
    factory.create_stars(stars)
    factory._create_random_ships(ships)
    return factory


def default_game():
    """Create and save a default game instance for testing purposes."""
    return default_game_factory().save()