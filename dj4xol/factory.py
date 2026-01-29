from dj4xol.starnamer import StarNamer
from .models import Game, Star, Ship, Player
import random

class GameFactory():
    """A factory class to draft and initialise game instances.
    The factory can create stars and ships, assign players to the game,
    and save the game to the database."""
    def __init__(self, game = None):
        self.starnamer = StarNamer()
        self.stars = []
        self.ships = []
        self.players = []
        self.owner = None
        if game:
            self.game = game
        else:
            self.game = Game()

    def new(self):
        """Create a new game instance."""
        self.game = Game()
        self.stars = []
        self.ships = []
        self.players = []
        return self.game
    
    def validate(self):
        """Validate the game instance before saving."""
        if not isinstance(self.game, Game):
            raise TypeError("game is not an instance of the Game model object")
        if self.owner is None:
            raise Exception("game owner not set")
        if not (self.game.map_size_x and self.game.map_size_y):
            raise Exception("map size not set")
        if self.game.map_size_x < 10 or self.game.map_size_y < 10:
            raise Exception("map size too small")
        if len(self.stars) < 1:
            raise Exception("no stars created")
        if len(self.players) < 1:
            raise Exception("no players assigned to game")
        return True

    def load(self, game):
        """Load an existing game instance into the factory."""
        if not isinstance(game, Game):
            raise TypeError("game is not an instance of the Game model object")
        self.game = game
        self.stars = list(game.stars.all())
        self.ships = list(game.ships.all())
        self.players = list(game.players.all())
        self.owner = game.owner
        return self

    def save(self):
        """Save the game and all stars to the database. 
        Returns the saved game model instance."""
        self.validate()
        self.game.save()
        self.game.owner = self.owner
        for star in self.stars:
            star.game = self.game
        Star.objects.bulk_create(self.stars)
        for player in self.players:
            self.game.players.add(player)
        self.game.save()
        self._assign_homeworlds()
        for ship in self.ships:
            ship.game = self.game
        Ship.objects.bulk_create(self.ships)
        self.game.save()
        return self.game
    
    def set_year(self, year):
        self.game.year = year
        return self

    def set_owner(self, owner):
        """Set the owner of the game. The owner is the first player to join the game."""
        if not isinstance(owner, Player):
            raise TypeError("owner is not an instance of the Player model object")
        self.owner = owner
        self.players.append(owner)
        return self
    
    def add_player(self, player):
        """Add a player to the game."""
        if not isinstance(player, Player):
            raise TypeError("player is not an instance of the Player model object")
        self.players.append(player)
        return self
    
    def remove_player(self, player):
        """Remove a player from the game."""
        if player in self.players:
            self.players.remove(player)
        return self

    def set_map_size(self, x, y):
        self.game.map_size_x = x
        self.game.map_size_y = y
        return self

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
        return self

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
        return self
    
    def _assign_homeworlds(self):
        """Assign a homeworld to each player in the game."""
        players = self.game.players.all()
        if len(players) > len(self.stars):
            raise Exception("not enough stars to assign homeworlds to all players")
        random.shuffle(self.stars)
        for i, player in enumerate(players):
            star = self.stars[i]
            star.player = player
            star.is_homeworld = True
        return self
    
    def _create_random_ships(self, ships):
        """Create ships for a player and place them randomly in the game. Used mainly for testing purposes."""
        for player in self.players:
            for _ in range(ships):
                name = self.starnamer.get_unique()
                x = random.randint(1, self.game.map_size_x)
                y = random.randint(1, self.game.map_size_y)
                self.ships.append(Ship(name=name, x=x, y=y, player=player))
        return self