from dj4xol.starnamer import StarNamer
from .models import Game, Star, Player
import random

class GameFactory():
    def __init__(self, game = None):
        self.starnamer = StarNamer()
        self.stars = []
        if game:
            self.game = game
        else:
            self.game = Game()

    def save(self):
        self.game.save()
        for star in self.stars:
            star.game = self.game
        Star.objects.bulk_create(self.stars)

    def set_owner(self, owner):
        if not isinstance(owner, Player):
            raise TypeError("owner is not an instance of the Player model object")
        self.game.owner = owner

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



