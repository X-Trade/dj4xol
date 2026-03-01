from datetime import timedelta
from django.utils import timezone
from dj4xol.starnamer import StarNamer
from .models import Game, Star, Fleet, Player, Account
from .research import get_player_tech_effects
from .fleet_thumbnails import choose_fleet_thumbnail
import random
import math

TURN_INTERVALS = {
    'HOURLY': timedelta(hours=1),
    'DAILY': timedelta(days=1),
    'WEEKLY': timedelta(weeks=1),
}

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
        # Set initial next_generation time for timed turn schemes
        interval = TURN_INTERVALS.get(self.game.turn_scheme)
        if interval:
            self.game.next_generation = timezone.now() + interval
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

    def _create_star_clusters(self, stars, system_size=6, cluster_radius=25, min_cluster_distance=40):
        """Create stars in clusters with better spacing."""
        min_x = 1
        min_y = 1
        max_x = self.game.map_size_x - 1
        max_y = self.game.map_size_y - 1
        
        cluster_centers = []
        created = 0
        
        while created < stars:
            # Find a cluster center that's far enough from existing clusters
            attempts = 0
            while attempts < 50:  # Prevent infinite loop
                cluster_x = random.randint(min_x + cluster_radius, max_x - cluster_radius)
                cluster_y = random.randint(min_y + cluster_radius, max_y - cluster_radius)
                
                # Check if this cluster center is far enough from existing ones
                too_close = False
                for cx, cy in cluster_centers:
                    distance = ((cluster_x - cx) ** 2 + (cluster_y - cy) ** 2) ** 0.5
                    if distance < min_cluster_distance:
                        too_close = True
                        break
                
                if not too_close:
                    break
                attempts += 1
            
            # If we couldn't find a good spot after many attempts, just use the last attempt
            cluster_centers.append((cluster_x, cluster_y))
            
            # Create stars in this cluster with more spread
            stars_in_cluster = min(system_size, stars - created)
            for _ in range(stars_in_cluster):
                name = self.starnamer.get_unique()
                # Use larger, more varied offsets for better spread
                angle = random.random() * 2 * math.pi  # Random angle
                radius = random.random() * cluster_radius  # Random distance from center
                ofs_x = int(radius * math.cos(angle))
                ofs_y = int(radius * math.sin(angle))
                
                x = max(min_x, min(max_x, cluster_x + ofs_x))
                y = max(min_y, min(max_y, cluster_y + ofs_y))
                
                self.stars.append(Star(name=name, x=x, y=y))
                created += 1
                
                if created >= stars:
                    break
        
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
        Transposes resource yields from 0-100% into 50-100%, and ensures
        surface minerals are at least 1000kt."""
        star.player = player
        if player.starting_colonists is not None:
            star.colonists = player.starting_colonists * 1000
        else:
            star.colonists = player.race_type.starting_population
        # Set environmentals to player's ideal (center) values
        star.gravity = player.gravity_center
        star.temperature = player.temperature_center
        star.radiation = player.radiation_center
        # Transpose homeworld yields from 0-100 into 50-100.
        star.ironium_yield = int(star.ironium_yield / 2.0 + 50)
        star.boranium_yield = int(star.boranium_yield / 2.0 + 50)
        star.germanium_yield = int(star.germanium_yield / 2.0 + 50)
        # Apply starting infrastructure
        star.mines = max(0, int(player.starting_mines or 0))
        star.factories = max(0, int(player.starting_factories or 0))
        star.labs = max(0, int(player.starting_labs or 0))
        star.shipyards = max(0, int(player.starting_shipyards or 0))
        # Ensure homeworld has minimum surface minerals (1000kt each)
        star.ironium_inventory = max(1000, star.ironium_inventory)
        star.boranium_inventory = max(1000, star.boranium_inventory)
        star.germanium_inventory = max(1000, star.germanium_inventory)
        # Apply leftover points to surface minerals (10kt per point) unless routed to research.
        if (player.leftover_points and player.leftover_points > 0 and
                not player.spend_leftover_points_on_research):
            total_kt = int(player.leftover_points * 10)
            if total_kt > 0:
                weights = [
                    max(1, star.ironium_yield),
                    max(1, star.boranium_yield),
                    max(1, star.germanium_yield),
                ]
                total_weight = sum(weights)
                base_alloc = [
                    int(total_kt * weights[0] / total_weight),
                    int(total_kt * weights[1] / total_weight),
                    int(total_kt * weights[2] / total_weight),
                ]
                remainder = total_kt - sum(base_alloc)
                for _ in range(remainder):
                    pick = random.choices([0, 1, 2], weights=weights, k=1)[0]
                    base_alloc[pick] += 1
                star.ironium_inventory += base_alloc[0]
                star.boranium_inventory += base_alloc[1]
                star.germanium_inventory += base_alloc[2]
        # Override star name if player has a homeworld name set
        if player.homeworld_name:
            star.name = player.homeworld_name
        star.save()
        player.homeworld = star
        player.save()
        return player

    def _resolve_starting_tech_level(self, race):
        requested_level = max(0, int(getattr(race, 'starting_tech_level', 0) or 0))
        max_allowed = max(0, int(getattr(self.game, 'max_starting_tech_level', 0) or 0))
        effective_level = min(requested_level, max_allowed)

        from .research import get_starting_tech_balance_cost
        requested_cost = float(get_starting_tech_balance_cost(requested_level))
        effective_cost = float(get_starting_tech_balance_cost(effective_level))
        refunded_points = max(0.0, requested_cost - effective_cost)
        return effective_level, refunded_points

    def _apply_starting_research_level(self, player):
        from .research import ensure_player_research_rows
        start_level = max(0, int(getattr(player, 'starting_tech_level', 0) or 0))
        rows = ensure_player_research_rows(player)
        for row in rows:
            row.current_level = float(start_level)
            row.stored_rp = 0.0
            row.save(update_fields=['current_level', 'stored_rp'])

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
            homeworld_name=race.homeworld_name,
            race_type=race.race_type,
        )
        player.starting_colonists = race.starting_colonists
        player.starting_mines = race.starting_mines
        player.starting_factories = race.starting_factories
        player.starting_labs = race.starting_labs
        player.starting_shipyards = race.starting_shipyards
        player.starting_fleets = race.starting_fleets
        effective_starting_tech_level, refunded_points = self._resolve_starting_tech_level(race)
        player.starting_tech_level = effective_starting_tech_level
        player.convert_unused_buildpoints_to_research = (
            race.convert_unused_buildpoints_to_research
        )
        player.singular_research = race.singular_research
        player.spend_leftover_points_on_research = race.spend_leftover_points_on_research
        player.leftover_points = float(race.leftover_points or 0.0) + float(refunded_points)
        player.copy_habitability_from(race)
        player.save()
        self._assign_homeworld_to_player(player, self._find_homeworld_star(available_stars))
        self._apply_starting_research_level(player)
        self._create_starting_fleets(player)
        return player

    def _create_starting_fleets(self, player):
        count = max(0, int(player.starting_fleets or 0))
        if count <= 0:
            return
        tech_effects = get_player_tech_effects(player)
        fleet_start_index = player.fleets.count()
        for i in range(count):
            fleet_number = fleet_start_index + i + 1
            fleet_name = f"{player.name} Fleet {fleet_number}"
            thumbnail_path = choose_fleet_thumbnail(
                f"{self.game.id}:{player.id}:{fleet_name}",
                tech_effects.get('hull_thumbnail_class'),
            )
            Fleet.objects.create(
                game=self.game,
                player=player,
                name=fleet_name,
                x=player.homeworld.x,
                y=player.homeworld.y,
                cargo_capacity=tech_effects.get('max_cargo_capacity', 100),
                fuel=tech_effects.get('max_fuel', 50.0),
                max_fuel=tech_effects.get('max_fuel', 50.0),
                max_safe_warp=tech_effects.get('max_warp_speed', 2),
                fuel_efficiency=tech_effects.get('fuel_efficiency', 1.0),
                overmax_fuel_penalty=tech_effects.get('overmax_fuel_penalty', 1.0),
                offense_level=tech_effects.get('offense_level', 0.0),
                defense_level=tech_effects.get('defense_level', 0.0),
                thumbnail_path=thumbnail_path,
            )
    
    def _create_random_fleets(self, count_per_player):
        """Create fleets for each player. Game must be saved first. For testing."""
        for player in self.game.players.all():
            for _ in range(count_per_player):
                Fleet.objects.create(
                    game=self.game,
                    player=player,
                    name=self.starnamer.get_unique(),
                    x=random.randint(1, self.game.map_size_x),
                    y=random.randint(1, self.game.map_size_y),
                    # Add some random cargo for testing
                    ironium_inventory=random.randint(0, 10000),
                    boranium_inventory=random.randint(0, 10000),
                    germanium_inventory=random.randint(0, 5000),
                    colonists=random.randint(0, 5000)
                )
        return self
