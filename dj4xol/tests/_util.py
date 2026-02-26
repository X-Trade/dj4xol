from ..factory import GameFactory
from ..models import Account, ServerRaceType, ServerRace
from django.contrib.auth.models import User


def get_default_race_type():
    """Get or create a default race type for testing."""
    race_type, _ = ServerRaceType.objects.get_or_create(
        code='TEST',
        defaults={'name': 'Test Race', 'description': 'Test race type'}
    )
    return race_type


def get_default_race():
    """Get or create a default race for testing."""
    race, _ = ServerRace.objects.get_or_create(
        name='Tester',
        defaults={
            'plural_name': 'Testers',
            'race_type': get_default_race_type(),
            'starting_tech_level': 0,
        }
    )
    if race.starting_tech_level != 0:
        race.starting_tech_level = 0
        race.save(update_fields=['starting_tech_level'])
    return race


def get_default_user():
    """Get or create a default user and account for testing."""
    user, created = User.objects.get_or_create(
        username='default_user',
        defaults={'email': 'test@example.com'}
    )
    if created:
        user.set_password('test')
        user.save()
    account, _ = Account.objects.get_or_create(django_user=user)
    return user, account


def default_game(stars=50, fleets=0):
    """Create a saved game with one player for testing."""
    _, account = get_default_user()
    factory = GameFactory()
    factory.set_map_size(100, 100)
    factory.set_owner(account)
    factory.create_stars(stars)
    game = factory.save()
    factory.join_player(account, get_default_race())
    if fleets:
        factory._create_random_fleets(fleets)
    return game


def default_game_factory(stars=50):
    """Create a factory with game ready to save (no players yet)."""
    _, account = get_default_user()
    factory = GameFactory()
    factory.set_map_size(100, 100)
    factory.set_owner(account)
    factory.create_stars(stars)
    return factory
