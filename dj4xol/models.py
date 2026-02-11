from django.db import models
from django.db.utils import IntegrityError
from django import forms
from django.contrib.auth import models as auth_models
from django.core.validators import MaxValueValidator, MinValueValidator
from itertools import chain
from .starnamer import StarNamer
import random
import uuid
from uuid_extensions import uuid7 as _uuid7


def uuid7():
    """Wrapper for uuid7 to help Django migration serialization."""
    return _uuid7()

def random_resource_init():
    """Legacy function for migrations. Uniform 0-100 distribution."""
    return random.randint(0, 100)


def random_ironium_yield():
    """Random ironium yield biased toward higher values. Average ~45%."""
    # Use a distribution that favours higher yields: 10-80% range, biased high
    base = random.random()
    # Shift the distribution toward higher values
    biased = 0.1 + (base ** 0.6) * 0.7  # Range 0.1-0.8, biased high
    return int(biased * 100)


def random_boranium_yield():
    """Random boranium yield, slightly rarer than ironium. Average ~35%."""
    base = random.random()
    biased = 0.05 + (base ** 0.8) * 0.65  # Range 0.05-0.7
    return int(biased * 100)


def random_germanium_yield():
    """Random germanium yield, rarest of the three. Average ~25%."""
    base = random.random()
    biased = (base ** 1.2) * 0.6  # Range 0-0.6, biased low
    return int(biased * 100)
def random_environmental_init():
    return random.random() * 2.0
def random_capacity_init():
    """Random base capacity between 5bn and 15bn (stored in millions)."""
    return random.randint(5000, 15000)
def random_surface_mineral_init():
    """Random surface minerals 0-1Mkt with exponential distribution (heavily biased toward lower values)."""
    return int((random.random() ** 50) * 1_000_000)


class HabitabilityMixin(models.Model):
    """Mixin providing habitability range fields and methods."""
    HABITABILITY_BUDGET = 6.0
    ENVS = ['gravity', 'temperature', 'radiation']

    gravity_center = models.FloatField(default=1.0)
    gravity_width = models.FloatField(default=1.0)
    temperature_center = models.FloatField(default=1.0)
    temperature_width = models.FloatField(default=1.0)
    radiation_center = models.FloatField(default=1.0)
    radiation_width = models.FloatField(default=1.0)

    class Meta:
        abstract = True

    def hab_min(self, env):
        """Get minimum habitable value for an environmental factor."""
        return getattr(self, f'{env}_center') - getattr(self, f'{env}_width') / 2

    def hab_max(self, env):
        """Get maximum habitable value for an environmental factor."""
        return getattr(self, f'{env}_center') + getattr(self, f'{env}_width') / 2

    def habitability_width_cost(self):
        """Total width points spent."""
        return sum(getattr(self, f'{env}_width') for env in self.ENVS)

    def habitability_center_cost(self):
        """Total center points spent (average centers cost more)."""
        return sum(1.0 - abs(getattr(self, f'{env}_center') - 1.0) for env in self.ENVS)

    def habitability_total_cost(self):
        """Total habitability points spent."""
        return self.habitability_width_cost() + self.habitability_center_cost()

    def validate_habitability(self):
        """Validate habitability configuration. Returns list of errors."""
        errors = []
        for env in self.ENVS:
            center = getattr(self, f'{env}_center')
            width = getattr(self, f'{env}_width')
            half = width / 2
            if center - half < 0.0:
                errors.append(f'{env.title()} range extends below 0')
            if center + half > 2.0:
                errors.append(f'{env.title()} range extends above 2')
            if width < 0:
                errors.append(f'{env.title()} width cannot be negative')
        if self.habitability_total_cost() > self.HABITABILITY_BUDGET:
            errors.append(f'Habitability cost ({self.habitability_total_cost():.2f}) exceeds budget ({self.HABITABILITY_BUDGET})')
        return errors

    def is_habitable(self, star):
        """Check if a star is within habitable range for all factors."""
        for env in self.ENVS:
            value = getattr(star, env)
            if value < self.hab_min(env) or value > self.hab_max(env):
                return False
        return True

    def copy_habitability_from(self, source):
        """Copy habitability fields from another object."""
        for env in self.ENVS:
            setattr(self, f'{env}_center', getattr(source, f'{env}_center'))
            setattr(self, f'{env}_width', getattr(source, f'{env}_width'))


class UUIDMixin(models.Model):
    """Mixin providing UUID primary key and short_id for URL-friendly identification."""
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    short_id = models.CharField(max_length=12, editable=False, unique=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.short_id:
            self.short_id = self.id.hex[-8:]
        super().save(*args, **kwargs)


class ServerSettings(models.Model):
    key = models.CharField(max_length=30, primary_key=True, unique=True)
    value = models.CharField(max_length=30)
    long_value = models.TextField(blank=True, default='')
    description = models.CharField(max_length=60)
    modified = models.DateTimeField(auto_now=True, null=True)
    modified_by = models.ForeignKey(auth_models.User, on_delete=models.PROTECT, null=True)

    _defaults_cache = None

    class Meta:
        verbose_name = 'Server Setting'
        verbose_name_plural = 'Server Settings'

    def __str__(self):
        return '%s' % (self.key)

    def to_dict(self):
        return {self.key: self.value}

    @classmethod
    def all_to_dict(cls):
        return {setting.key: setting.value for setting in ServerSettings.objects.all()}

    @classmethod
    def _load_defaults(cls):
        """Load defaults from fixtures file."""
        if cls._defaults_cache is None:
            import yaml
            import os
            fixtures_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'defaults.yaml')
            with open(fixtures_path, 'r') as f:
                data = yaml.safe_load(f)
            cls._defaults_cache = {
                item['fields']['key']: item['fields']
                for item in data if item['model'] == 'dj4xol.ServerSettings'
            }
        return cls._defaults_cache

    @classmethod
    def get(cls, key, default=None):
        """Get a setting by key, creating from fixtures if not found.

        Returns long_value if set, otherwise value.
        """
        try:
            setting = cls.objects.get(pk=key)
            return setting.long_value or setting.value
        except cls.DoesNotExist:
            defaults = cls._load_defaults()
            if key in defaults:
                fields = defaults[key]
                setting = cls.objects.create(
                    key=key,
                    value=fields.get('value', ''),
                    long_value=fields.get('long_value', ''),
                    description=fields.get('description', '')
                )
                return setting.long_value or setting.value
            return default


class Account(models.Model):
    """A dj4xol account linked to a Django user."""
    THEME_CHOICES = [
        ('classic', 'Classic'),
        ('lcars', 'LCARS'),
        ('win95', 'Windows 95'),
    ]

    django_user = models.OneToOneField(auth_models.User, primary_key=True,
            related_name="dj4xol_account", on_delete=models.PROTECT)
    full_name = models.CharField(max_length=60)
    alias = models.CharField(max_length=30, unique=True)
    email = models.EmailField()
    theme = models.CharField(max_length=20, choices=THEME_CHOICES, default='classic')
    website_url = models.URLField(blank=True, default='')

    def save(self, *args, **kwargs):
        if not self.alias:
            self.alias = self.django_user.username
        super(Account, self).save(*args, **kwargs)

    def __str__(self):
        if self.pk:
            return '%i:%s' % (self.pk, self.alias)
        return self.alias or '(new account)'


class Game(UUIDMixin):
    TURN_SCHEME_CHOICES = [
        ('QUORUM', 'Quorum - when all players are ready'),
        ('OWNER', 'Owner - when game owner triggers'),
        ('HOURLY', 'Hourly'),
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
    ]

    name = models.CharField(max_length=30)
    owner = models.ForeignKey(Account, related_name="owned_games",
            on_delete=models.SET_NULL, null=True)
    description = models.TextField(blank=True, default='')
    map_size_x = models.IntegerField()
    map_size_y = models.IntegerField()
    joinable = models.BooleanField(default=False)  # anybody who can see can join
    public = models.BooleanField(default=False)  # anybody can view
    ended = models.BooleanField(default=False)
    year = models.IntegerField(default=2400)
    join_until_year = models.IntegerField(null=True, blank=True)  # auto-close joining after this year
    max_players = models.IntegerField(null=True, blank=True)  # max players allowed
    turn_scheme = models.CharField(max_length=10, choices=TURN_SCHEME_CHOICES, default='QUORUM')
    years_per_turn = models.IntegerField(default=1)
    random_events = models.BooleanField(default=False)
    last_generated = models.DateTimeField(null=True, blank=True)
    next_generation = models.DateTimeField(null=True, blank=True)
    is_generating = models.BooleanField(default=False)

    _star_names = []
    _star_namer = None

    def __str__(self):
        return f'{self.short_id} {self.name}'

    def get_star_names(self):
        return [star["name"] for star in self.stars.values("name").all()]

    def get_object_at(self, x, y):
        return self.stars.filter(x=x, y=y).first() or self.fleets.filter(x=x, y=y).first() or None

    def get_all_objects_at(self, x, y):
        return list(chain(
            self.stars.filter(x=x, y=y).all(),
            self.fleets.filter(x=x, y=y).all(),
            self.salvages.filter(x=x, y=y).all()
        ))

    def get_star_namer(self):
        if not self._star_namer:
            self._star_namer = StarNamer(self.get_star_names())
        return self._star_namer

    def get_turn_scheme_short_display(self):
        """Get short friendly name for turn scheme (without description)."""
        full_display = self.get_turn_scheme_display()
        # Split on ' - ' and take first part for short display
        return full_display.split(' - ')[0] if ' - ' in full_display else full_display


class AbstractGameObject(UUIDMixin):
    game = models.ForeignKey(Game, related_name="%(class)ss",
            on_delete=models.CASCADE)

    def __str__(self):
        return self.short_id

    def save(self, *args, **kwargs):
        # Only generate short_id for new objects (existing ones keep their short_id)
        if not self.short_id:
            # Generate deterministic short_id using XOR approach for better entropy distribution
            uuid_int = self.id.int
            self.short_id = self._generate_short_id_from_uuid(uuid_int)

        super(UUIDMixin, self).save(*args, **kwargs)

    def _generate_short_id_from_uuid(self, uuid_int):
        """Generate short_id by XORing UUID chunks for better entropy distribution."""
        # XOR the 128-bit UUID in 32-bit chunks to get 32 bits
        chunk1 = (uuid_int >> 96) & 0xFFFFFFFF  # Top 32 bits
        chunk2 = (uuid_int >> 64) & 0xFFFFFFFF  # Next 32 bits
        chunk3 = (uuid_int >> 32) & 0xFFFFFFFF  # Next 32 bits
        chunk4 = uuid_int & 0xFFFFFFFF          # Bottom 32 bits

        # XOR all chunks together
        xor_result = chunk1 ^ chunk2 ^ chunk3 ^ chunk4

        # Add game prefix for scoping
        game_prefix = self.game.short_id[:4]

        # Convert to base36 (0-9, a-z) for readability, take 8 chars to fit in 12 total
        import string
        base36_chars = string.digits + string.ascii_lowercase

        short_part = ''
        temp = xor_result
        for _ in range(8):  # Generate 8 characters
            short_part = base36_chars[temp % 36] + short_part
            temp //= 36

        return game_prefix + short_part

    class Meta:
        abstract = True


class AbstractMapObject(AbstractGameObject):
    x = models.IntegerField()
    y = models.IntegerField()

    class Meta:
        abstract = True


class ServerRaceType(HabitabilityMixin):
    code = models.CharField(max_length=4, primary_key=True, unique=True)
    name = models.CharField(max_length=16)
    enabled = models.BooleanField(default=True)
    description = models.TextField()
    starting_population = models.IntegerField(default=1000)
    starting_planets = models.IntegerField(default=1)
    starting_planet_has_stargate = models.BooleanField(default=False)
    starting_planet_has_massdriver = models.BooleanField(default=False)
    population_growth_multiplier = models.FloatField(default=1.0)
    population_growth_uses_resources = models.BooleanField(default=False)
    starting_economy = models.IntegerField(default=2)
    economy_offset = models.IntegerField(default=0)
    manufacturing_multiplier = models.FloatField(default=1.0)
    combat_multiplier = models.FloatField(default=1.0)
    defence_multiplier = models.FloatField(default=1.0)
    bombardment_multiplier = models.FloatField(default=1.0)
    ground_force_multiplier = models.FloatField(default=1.0)
    diplomacy_multiplier = models.FloatField(default=1.0)
    trade_multiplier = models.FloatField(default=1.0)
    scan_multiplier = models.FloatField(default=1.0)
    shield_multiplier = models.FloatField(default=1.0)
    warp_multiplier = models.FloatField(default=1.0)
    stealth_multiplier = models.FloatField(default=1.0)
    terraforming_multiplier = models.FloatField(default=1.0)
    metalurgy_multiplier = models.FloatField(default=1.0)
    political_stability = models.FloatField(default=1.0)
    luck_multiplier = models.FloatField(default=1.0)
    persuasion_multiplier = models.FloatField(default=1.0)
    chance_of_scantheft = models.FloatField(default=0.01)
    ignores_radiation = models.BooleanField(default=False)
    ignores_temperature = models.BooleanField(default=False)
    ignores_gravity = models.BooleanField(default=False)
    requires_space_station = models.BooleanField(default=False)
    has_terraforming = models.BooleanField(default=True)
    has_advanced_mines = models.BooleanField(default=False)
    has_advanced_stargates = models.BooleanField(default=False)
    has_advanced_remoteminers = models.BooleanField(default=False)
    has_advanced_hulls = models.BooleanField(default=False)
    has_superweapon = models.BooleanField(default=False)
    has_bombs = models.BooleanField(default=True)
    has_metalurgy = models.BooleanField(default=True)
    has_stealth = models.BooleanField(default=True)
    has_generalised_research = models.BooleanField(default=False)
    is_parasitic = models.BooleanField(default=False)
    is_cybernetic = models.BooleanField(default=False)
    is_mechanical = models.BooleanField(default=False)
    is_energy_being = models.BooleanField(default=False)
    starting_research_points = models.IntegerField(default=3)
    research_multiplier = models.FloatField(default=1.0)
    initiative_multiplier = models.FloatField(default=1.0)
    cargo_multiplier = models.FloatField(default=1.0)

    def __str__(self):
        return self.name


class Salvage(AbstractMapObject):
    """Recoverable minerals left behind when vessels are destroyed or scuttled."""
    ironium_inventory = models.IntegerField(default=0)
    boranium_inventory = models.IntegerField(default=0)
    germanium_inventory = models.IntegerField(default=0)

    @property
    def total_minerals(self):
        """Total minerals in this salvage pile."""
        return (self.ironium_inventory + self.boranium_inventory +
                self.germanium_inventory)

    @property
    def name(self):
        """Display name for salvage."""
        return f"Salvage ({self.x}, {self.y})"

    @property
    def player(self):
        """Salvage is neutral - no owner."""
        return None

    class Meta:
        unique_together = [['game', 'x', 'y']]


class Fleet(AbstractMapObject):
    """A group of ships traveling together."""
    name = models.CharField(max_length=30)
    player = models.ForeignKey('Player', related_name='fleets',
            on_delete=models.CASCADE)
    # Heading in degrees: 0 = north, 90 = east, 180 = south, 270 = west
    heading = models.FloatField(default=0.0)
    ship_count = models.IntegerField(default=1)

    # Cargo capacity and inventory
    cargo_capacity = models.IntegerField(default=100)  # Total cargo capacity in kt
    ironium_inventory = models.IntegerField(default=0)  # Current ironium cargo in kt
    boranium_inventory = models.IntegerField(default=0)  # Current boranium cargo in kt
    germanium_inventory = models.IntegerField(default=0)  # Current germanium cargo in kt
    colonists = models.IntegerField(default=0)  # Current colonist cargo in thousands
    dry_mass = models.IntegerField(default=100)  # Dry mass in kt for colonise bonus
    max_safe_warp = models.IntegerField(default=5)
    integrity = models.IntegerField(default=100,
            validators=[MinValueValidator(0), MaxValueValidator(100)])

    @property
    def cargo_used(self):
        """Total cargo currently loaded (in kt equivalent)."""
        return self.ironium_inventory + self.boranium_inventory + self.germanium_inventory + self.colonists

    @property
    def cargo_remaining(self):
        """Remaining cargo capacity (in kt equivalent)."""
        return self.cargo_capacity - self.cargo_used


class Star(AbstractMapObject):
    name = models.CharField(max_length=30)
    player = models.ForeignKey('Player', null=True, default=None,
            related_name='stars', on_delete=models.SET_NULL)

    gravity = models.FloatField(default=random_environmental_init,
                                validators=[MinValueValidator(0.0), MaxValueValidator(2.0)])
    temperature = models.FloatField(default=random_environmental_init,
                                validators=[MinValueValidator(0.0), MaxValueValidator(2.0)])
    radiation = models.FloatField(default=random_environmental_init,
                                validators=[MinValueValidator(0.0), MaxValueValidator(2.0)])

    # Mineral yields (percentage, 0-100%)
    ironium_yield = models.IntegerField(default=random_ironium_yield,
                                        validators=[MinValueValidator(0), MaxValueValidator(100)])
    boranium_yield = models.IntegerField(default=random_boranium_yield,
                                         validators=[MinValueValidator(0), MaxValueValidator(100)])
    germanium_yield = models.IntegerField(default=random_germanium_yield,
                                          validators=[MinValueValidator(0), MaxValueValidator(100)])

    # Surface mineral inventory (kt)
    ironium_inventory = models.IntegerField(default=random_surface_mineral_init)
    boranium_inventory = models.IntegerField(default=random_surface_mineral_init)
    germanium_inventory = models.IntegerField(default=random_surface_mineral_init)

    colonists = models.IntegerField(default=0)
    # Base carrying capacity (in millions), effective capacity = base * habitability
    base_capacity = models.IntegerField(default=random_capacity_init)

    # Economic infrastructure
    mines = models.IntegerField(default=0)
    factories = models.IntegerField(default=0)
    defenses = models.IntegerField(default=0)
    shipyards = models.IntegerField(default=0)
    buildpoints_consumed = models.IntegerField(default=0)  # Reset each turn


class ServerRace(UUIDMixin, HabitabilityMixin):
    name = models.CharField(max_length=16)
    plural_name = models.CharField(max_length=16)
    homeworld_name = models.CharField(max_length=30, blank=True, default='')
    public = models.BooleanField(default=False)
    owner = models.ForeignKey(Account, related_name="custom_races",
                                      null=True, default=None,
                                      on_delete=models.SET_NULL)
    description = models.TextField(blank=True, default='')
    race_type = models.ForeignKey(ServerRaceType)

    def __str__(self):
        return self.name


class Player(AbstractGameObject, HabitabilityMixin):
    """A player instance in a game, with their chosen race."""
    account = models.ForeignKey(Account, related_name="players",
                                null=True, default=None,
                                on_delete=models.SET_NULL)
    name = models.CharField(max_length=16)
    plural_name = models.CharField(max_length=16, null=True, default=None)
    homeworld_name = models.CharField(max_length=30, blank=True, default='')
    homeworld = models.ForeignKey(Star, null=True, default=None,
                                  related_name="homeworld_of",
                                  on_delete=models.SET_NULL)
    description = models.TextField(blank=True, default='')
    race_type = models.ForeignKey(ServerRaceType)
    turned_in = models.BooleanField(default=False)
    last_seen_year = models.IntegerField(null=True, blank=True)
    messages_seen_year = models.IntegerField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.plural_name is None:
            self.plural_name = self.name + 's'
        super(Player, self).save(*args, **kwargs)


class FleetOrders(AbstractGameObject):
    """Movement and action orders for a fleet."""
    ORDER_TYPE_CHOICES = [
        ('MOVE', 'Move'),
        ('INTERCEPT', 'Intercept'),
        ('TRANSFER', 'Transfer'),
        ('COLONISE', 'Colonise'),
        ('MERGE', 'Merge'),
        ('SCUTTLE', 'Scuttle'),
        ('PATROL', 'Patrol'),
    ]

    fleet = models.ForeignKey(Fleet, related_name="orders",
            on_delete=models.CASCADE)
    order_type = models.CharField(max_length=10, choices=ORDER_TYPE_CHOICES, default='MOVE')
    repeat = models.BooleanField(default=False)
    position = models.IntegerField(default=0)

    # Movement parameters
    warpfactor = models.IntegerField(default=0,
                                     validators=[MinValueValidator(0), MaxValueValidator(13)])
    x = models.IntegerField(null=True)
    y = models.IntegerField(null=True)
    target_star = models.ForeignKey(Star, null=True, related_name='+',
            on_delete=models.CASCADE)
    target_fleet = models.ForeignKey(Fleet, null=True, related_name='+',
            on_delete=models.CASCADE)
    target_salvage = models.ForeignKey(Salvage, null=True, related_name='+',
            on_delete=models.CASCADE)

    # Transfer parameters
    TRANSFER_TYPE_CHOICES = [
        ('LOAD', 'Load'),
        ('UNLOAD', 'Unload'),
        ('UNLOAD_ALL', 'Unload All'),
    ]
    transfer_type = models.CharField(max_length=10, choices=TRANSFER_TYPE_CHOICES,
                                   null=True, blank=True)
    transfer_ironium = models.IntegerField(default=0)  # Amount to transfer
    transfer_boranium = models.IntegerField(default=0)
    transfer_germanium = models.IntegerField(default=0)
    transfer_colonists = models.IntegerField(default=0)

    # Patrol parameters
    patrol_radius = models.IntegerField(default=0)
    intercept_speed = models.IntegerField(default=5)

    @property
    def target(self):
        """Return a string description of the order target."""
        if self.target_star:
            return self.target_star.name
        elif self.target_fleet:
            return f"Fleet {self.target_fleet.name}"
        elif self.target_salvage:
            return f"Salvage ({self.target_salvage.x}, {self.target_salvage.y})"
        elif self.x is not None and self.y is not None:
            return f"({self.x}, {self.y})"
        else:
            return "Unknown destination"

    def target_is_star(self):
        return self.target_star_id is not None

    def target_is_fleet(self):
        return self.target_fleet_id is not None

    def target_is_salvage(self):
        return self.target_salvage_id is not None

    def has_target_coordinates(self):
        return self.x is not None and self.y is not None

    def get_actual_target(self):
        """Return canonical target and coordinates.

        Prefers explicit target objects when present and valid, otherwise falls
        back to explicit x/y coordinates. Returns (obj, x, y, kind).
        """
        if self.target_star_id:
            try:
                obj = self.target_star
                return obj, obj.x, obj.y, 'star'
            except Star.DoesNotExist:
                if self.has_target_coordinates():
                    return None, self.x, self.y, 'space'
                return None, None, None, 'none'
        if self.target_fleet_id:
            try:
                obj = self.target_fleet
                return obj, obj.x, obj.y, 'fleet'
            except Fleet.DoesNotExist:
                if self.has_target_coordinates():
                    return None, self.x, self.y, 'space'
                return None, None, None, 'none'
        if self.target_salvage_id:
            try:
                obj = self.target_salvage
                return obj, obj.x, obj.y, 'salvage'
            except Salvage.DoesNotExist:
                if self.has_target_coordinates():
                    return None, self.x, self.y, 'space'
                return None, None, None, 'none'
        if self.has_target_coordinates():
            return None, self.x, self.y, 'space'
        return None, None, None, 'none'

    def get_destination_coordinates(self):
        """Get the (x, y) coordinates for this order's destination.

        Uses the same logic as turn.py move_fleet() method.
        Returns tuple (x, y) or raises exception if no valid destination.
        """
        if self.target_star:
            return self.target_star.x, self.target_star.y
        elif self.target_fleet:
            return self.target_fleet.x, self.target_fleet.y
        elif self.target_salvage:
            return self.target_salvage.x, self.target_salvage.y
        elif self.has_target_coordinates():
            return self.x, self.y
        else:
            raise ValueError(f"Invalid order {self.id} - no valid destination")

    def save(self, *args, **kwargs):
        if self.pk is None and (self.position is None or self.position == 0):
            max_pos = FleetOrders.objects.filter(
                fleet=self.fleet
            ).aggregate(models.Max('position'))['position__max'] or 0
            self.position = max_pos + 1
        super(FleetOrders, self).save(*args, **kwargs)


class GameMessage(AbstractGameObject):
    CATEGORY_CHOICES = [
        ('GENERAL', 'General'),
        ('DIPLOMATIC', 'Diplomatic'),
        ('ENVIRONMENTAL', 'Environmental'),
        ('POPULATION', 'Population'),
        ('RANDOM', 'Random Event'),
        ('COMBAT', 'Combat'),
        ('PRODUCTION', 'Production'),
        ('EXCEPTION', 'Exception'),
    ]

    player = models.ForeignKey(Player, related_name='messages',
            on_delete=models.CASCADE)
    message = models.TextField()
    year = models.IntegerField()
    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES, default='GENERAL')
    priority = models.BooleanField(default=False)  # Important events: failed orders, attacks, etc.

    def save(self, *args, **kwargs):
        if self.year is None:
            self.year = self.game.year
        super(GameMessage, self).save(*args, **kwargs)


class GameInvitation(UUIDMixin):
    """Invitation to join a game, by account or email."""
    game = models.ForeignKey(Game, related_name='invitations', on_delete=models.CASCADE)
    account = models.ForeignKey(Account, null=True, blank=True,
                                related_name='game_invitations', on_delete=models.CASCADE)
    email = models.EmailField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['game', 'account'], ['game', 'email']]

    def __str__(self):
        target = self.account.alias if self.account else self.email
        return f'{self.game.name}: {target}'


PRODUCTION_COSTS = {
    'BUILD_MINE': {'bp': 0, 'ironium': 10, 'boranium': 0, 'germanium': 0, 'colonists': 1000},
    'BUILD_FACTORY': {'bp': 0, 'ironium': 20, 'boranium': 0, 'germanium': 0, 'colonists': 1000},
    'BUILD_DEFENSE': {'bp': 20, 'ironium': 100, 'boranium': 50, 'germanium': 50, 'colonists': 0},
    'BUILD_SHIPYARD': {'bp': 100, 'ironium': 250, 'boranium': 50, 'germanium': 100,
                       'colonists': 0},
    'BUILD_FLEET': {'bp': 50, 'ironium': 100, 'boranium': 200, 'germanium': 200, 'colonists': 0},
    'TERRAFORM_GRAVITY': {'bp': 100, 'ironium': 1000, 'boranium': 0, 'germanium': 0, 'colonists': 0},
    'TERRAFORM_TEMPERATURE': {'bp': 100, 'ironium': 0, 'boranium': 1000, 'germanium': 0, 'colonists': 0},
    'TERRAFORM_RADIATION': {'bp': 100, 'ironium': 0, 'boranium': 500, 'germanium': 500, 'colonists': 0},
}


class ProductionOrder(AbstractGameObject):
    """Production order for a star/planet."""
    ORDER_TYPES = [
        ('TERRAFORM_GRAVITY', 'Terraform Gravity (1%)'),
        ('TERRAFORM_TEMPERATURE', 'Terraform Temperature (1%)'),
        ('TERRAFORM_RADIATION', 'Terraform Radiation (1%)'),
        ('BUILD_FLEET', 'Build Fleet'),
        ('BUILD_MINE', 'Build Mine'),
        ('BUILD_FACTORY', 'Build Factory'),
        ('BUILD_DEFENSE', 'Build Defense'),
        ('BUILD_SHIPYARD', 'Build Shipyard'),
    ]

    star = models.ForeignKey(Star, related_name='production_orders',
            on_delete=models.CASCADE)
    order_type = models.CharField(max_length=24, choices=ORDER_TYPES)
    position = models.IntegerField(default=0)
    repeat = models.BooleanField(default=False)
    quantity = models.IntegerField(default=1)
    completed = models.IntegerField(default=0)
    # Track partial progress on current item (resources must be spent before BP)
    spent_ironium = models.IntegerField(default=0)
    spent_boranium = models.IntegerField(default=0)
    spent_germanium = models.IntegerField(default=0)
    spent_bp = models.IntegerField(default=0)

    class Meta:
        ordering = ['position']


class Report(AbstractGameObject):
    """Cached exploration report for a player about a game object.

    Each player maintains their own reports - players cannot see each other's
    reports. The unique_together constraint ensures one report per player per
    target, with the latest report overwriting previous ones.
    """
    TARGET_TYPE_CHOICES = [
        ('star', 'Star'),
        ('fleet', 'Fleet'),
        ('salvage', 'Salvage'),
    ]

    player = models.ForeignKey(Player, related_name='reports',
                               on_delete=models.CASCADE)
    year = models.IntegerField()
    target_type = models.CharField(max_length=10, choices=TARGET_TYPE_CHOICES)
    target_id = models.UUIDField()
    cached_report = models.TextField()  # JSON-serialised report data

    class Meta:
        unique_together = [['player', 'target_type', 'target_id']]

    def __str__(self):
        return f'{self.player.name} report on {self.target_type} {self.target_id}'

    def get_report_data(self):
        """Deserialise and return the cached report as a dictionary."""
        import json
        return json.loads(self.cached_report) if self.cached_report else {}

    def set_report_data(self, data):
        """Serialise and store the report data."""
        import json
        self.cached_report = json.dumps(data)
