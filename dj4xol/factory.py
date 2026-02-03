from dj4xol.starnamer import StarNamer
from .models import Game, Star, Fleet, Player, Account
import random
import math

class GameFactory():
    """A factory class to draft and initialise game instances.
    The factory can create stars and ships, assign players to the game,
    and save the game to the database."""
    def __init__(self, game=None):
        self.starnamer = StarNamer()
        self.stars = []
        self.owner = None
        self.game = game or Game()

    def new(self):
        """Create a new game instance."""
        self.game = Game()
        self.stars = []
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
        return True

    def load(self, game):
        """Load an existing game instance into the factory."""
        if not isinstance(game, Game):
            raise TypeError("game is not an instance of the Game model object")
        self.game = game
        self.owner = game.owner
        return self

    def save(self):
        """Save the game and stars to the database.
        Returns the saved game model instance. Use join_player() to add players."""
        self.validate()
        self.game.owner = self.owner
        self.game.save()
        for star in self.stars:
            star.game = self.game
            if not star.short_id:
                star.short_id = self.game.short_id[:4] + star.id.hex[-8:]
        Star.objects.bulk_create(self.stars)
        return self.game
    
    def set_year(self, year):
        self.game.year = year
        return self

    def set_owner(self, account):
        """Set the owner of the game (the Account that created it)."""
        if not isinstance(account, Account):
            raise TypeError("owner is not an instance of the Account model object")
        self.owner = account
        return self

    def set_map_size(self, x, y):
        self.game.map_size_x = x
        self.game.map_size_y = y
        return self

    def create_stars(self, stars, clusters=False, systems=False):
        if not (self.game.map_size_x or self.game.map_size_y):
            raise Exception("cannot add stars to game until map size is set")
        if clusters:
            self._create_star_clusters(stars)
        else:
            self._create_random_stars(stars)
        if systems:
            self._add_systems()
        return self

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
            for _ in range(1, system_size):
                name = self.starnamer.get_unique()
                ofs_x = random.randint(-8, 8)
                ofs_y = random.randint(-8, 8)
                x = cluster_x + ofs_x
                y = cluster_y + ofs_y
                self.stars.append(Star(name=name, x=x, y=y))
                created += 1
        return self

    def _add_systems(self):
        """Add 1-5 companion stars to 25% of existing stars at the same coordinates.

        Uses squared distribution so 1 companion is most common, 5 is rare.
        """
        num_systems = len(self.stars) // 4  # 25% of stars become systems
        system_stars = random.sample(self.stars, num_systems)
        for star in system_stars:
            # Squared distribution: bias towards lower numbers
            # random()**2 gives 0-1 biased towards 0, scale to 1-5
            companions = int(1 + 4 * (random.random() ** 2))
            for _ in range(companions):
                name = self.starnamer.get_unique()
                self.stars.append(Star(name=name, x=star.x, y=star.y))
        return self
    
    def _distance(self, star1, star2):
        """Calculate distance between two stars."""
        return math.sqrt((star1.x - star2.x) ** 2 + (star1.y - star2.y) ** 2)

    def _min_homeworld_distance(self):
        """Minimum distance between homeworlds: 250ly or 25% of shortest dimension."""
        return min(250, min(self.game.map_size_x, self.game.map_size_y) * 0.25)

    def _find_homeworld_star(self, available_stars):
        """Find a suitable star for a homeworld, respecting minimum distance from others."""
        existing_homeworlds = [p.homeworld for p in self.game.players.select_related('homeworld')
                              if p.homeworld]
        if not existing_homeworlds:
            return random.choice(available_stars)

        min_dist = self._min_homeworld_distance()

        # Find stars far enough from all existing homeworlds
        suitable = [s for s in available_stars
                    if all(self._distance(s, hw) >= min_dist for hw in existing_homeworlds)]

        if suitable:
            return random.choice(suitable)

        # Fallback: pick the star with maximum distance to nearest homeworld
        return max(available_stars, key=lambda s: min(self._distance(s, hw) for hw in existing_homeworlds))

    def _assign_homeworld_to_player(self, player, star):
        """Assign a specific star as homeworld to a player with starting population.
        Sets star environmentals to player's habitable centers and optionally renames.
        Ensures resource yields are at least 50% and surface minerals at least 1000kt."""
        star.player = player
        star.colonists = player.race_type.starting_population
        # Set environmentals to player's ideal (center) values
        star.gravity = player.gravity_center
        star.temperature = player.temperature_center
        star.radiation = player.radiation_center
        # Ensure homeworld has good resource yields (at least 50%)
        star.ironium = max(50, star.ironium)
        star.boranium = max(50, star.boranium)
        star.germanium = max(50, star.germanium)
        # Ensure homeworld has minimum surface minerals (1000kt each)
        star.ironium_surface = max(1000, star.ironium_surface)
        star.boranium_surface = max(1000, star.boranium_surface)
        star.germanium_surface = max(1000, star.germanium_surface)
        # Override star name if player has a homeworld name set
        if player.homeworld_name:
            star.name = player.homeworld_name
        star.save()
        player.homeworld = star
        player.save()
        return player

    def join_player(self, account, race, invited=False):
        """Add a player to an existing game with homeworld assignment.
        Returns the created Player instance or None if joining failed.
        Game owner and invited players can join non-joinable games."""
        is_owner = (account == self.game.owner)
        can_bypass = is_owner or invited

        if not can_bypass:
            if not self.game.joinable:
                return None
            if self.game.max_players and self.game.players.count() >= self.game.max_players:
                return None

        if self.game.players.filter(account=account).exists():
            return None

        available_stars = list(self.game.stars.filter(player=None))
        if not available_stars:
            return None

        player = Player(
            game=self.game,
            account=account,
            name=race.name,
            plural_name=race.plural_name,
            formal_name=race.formal_name,
            homeworld_name=race.homeworld_name,
            race_type=race.race_type,
        )
        player.copy_habitability_from(race)
        player.save()
        self._assign_homeworld_to_player(player, self._find_homeworld_star(available_stars))
        return player
    
    def _create_random_fleets(self, count_per_player):
        """Create fleets for each player. Game must be saved first. For testing."""
        for player in self.game.players.all():
            for _ in range(count_per_player):
                Fleet.objects.create(
                    game=self.game,
                    player=player,
                    name=self.starnamer.get_unique(),
                    x=random.randint(1, self.game.map_size_x),
                    y=random.randint(1, self.game.map_size_y)
                )
        return self