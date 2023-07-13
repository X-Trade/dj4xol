from dj4xol.starnamer import StarNamer
from .models import Game, Star, Ship, Player
import random

class GameFactory():
    def __init__(self, game = None):
        self.starnamer = StarNamer()
        self.stars = []
        self.ships = []
        if game:
            self.game = game
        else:
            self.game = Game()

    def save(self):
        """Save the game and all stars to the database."""
        self.game.save()
        for star in self.stars:
            star.game = self.game
        Star.objects.bulk_create(self.stars)
        for ship in self.ships:
            ship.game = self.game
        Ship.objects.bulk_create(self.ships)
        self.game.save()

    def set_owner(self, owner):
        """Set the owner of the game. The owner is the first player to join the game."""
        if not isinstance(owner, Player):
            raise TypeError("owner is not an instance of the Player model object")
        self.game.owner = owner
        self.game.players.add(owner)

    def set_map_size(self, x, y):
        self.game.map_size_x = x
        self.game.map_size_y = y

    def create_stars(self, stars, clusters=False):
        if not (self.game.map_size_x or self.game.map_size_y):
            raise Exception("cannot add stars to game until map size is set")
        if clusters:
            return self._create_star_clusters(stars)
        else:
            return self._create_random_stars(stars)

    def _create_random_stars(self, stars):
        """Create stars randomly in the game."""
        min_x = 1
        min_y = 1
        max_x = self.game.map_size_x - 1
        max_y = self.game.map_size_y - 1
        for _ in range(stars):
            x = random.randint(min_x, max_x)
            y = random.randint(min_y, max_y)
            name = self.starnamer.get_unique()
            self.stars.append(Star(name=name, x=x, y=y))

    def _create_star_clusters(self, stars, system_size=8):
        """Create stars in clusters, each with a maximum number of stars."""
        min_x = 1
        min_y = 1
        max_x = self.game.map_size_x - 1
        max_y = self.game.map_size_y - 1
        created = 0
        while created < stars:
            cluster_x = random.randint(min_x + 10, max_x - 10)
            cluster_y = random.randint(min_y + 10, max_y - 10)
            for _ in range(1,system_size):
                name = self.starnamer.get_unique()
                ofs_x = random.randint(-8, 8)
                ofs_y = random.randint(-8, 8)
                x = cluster_x + ofs_x
                y = cluster_y + ofs_y
                self.stars.append(Star(name=name, x=x, y=y))
                created += 1
    
    def _create_random_ships(self, ships):
        """Create ships for a player and place them randomly in the game. Used mainly for testing purposes."""
        for player in self.game.players.all():
            for _ in range(ships):
                name = self.starnamer.get_unique()
                x = random.randint(1, self.game.map_size_x)
                y = random.randint(1, self.game.map_size_y)
                self.ships.append(Ship(name=name, x=x, y=y, player=player))

