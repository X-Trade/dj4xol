from django.db import models
from django.db.utils import IntegrityError
from django import forms
from django.contrib.auth import models as auth_models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.exceptions import ValidationError
from itertools import chain
from .starnamer import StarNamer
from .habitability_rules import HabitabilityRules
from .fleet_thumbnails import choose_fleet_thumbnail
from .star_thumbnails import choose_star_thumbnail
from . import mineral_rules
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
    """Compatibility wrapper for migrations/defaults serialization."""
    return mineral_rules.random_ironium_yield()


def random_boranium_yield():
    """Compatibility wrapper for migrations/defaults serialization."""
    return mineral_rules.random_boranium_yield()


def random_germanium_yield():
    """Compatibility wrapper for migrations/defaults serialization."""
    return mineral_rules.random_germanium_yield()
def random_environmental_init():
    return random.random() * 2.0
def random_capacity_init():
    """Random base capacity between 5bn and 15bn (stored in millions)."""
    return random.randint(5000, 15000)


def random_surface_mineral_init():
    """Compatibility wrapper for migrations/defaults serialization."""
    return mineral_rules.random_surface_mineral_init()


def random_surface_ironium_init():
    """Compatibility wrapper for migrations/defaults serialization."""
    return mineral_rules.random_surface_ironium_init()


def random_surface_boranium_init():
    """Compatibility wrapper for migrations/defaults serialization."""
    return mineral_rules.random_surface_boranium_init()


def random_surface_germanium_init():
    """Compatibility wrapper for migrations/defaults serialization."""
    return mineral_rules.random_surface_germanium_init()


def random_heading_init():
    """Random heading in degrees, where 0 = north."""
    return random.random() * 360.0


def random_anomaly_stability_init():
    """Natural anomalies now start at fixed baseline stability."""
    return 50


def random_wormhole_stability_init():
    """Natural wormholes now start at fixed baseline stability."""
    return 50


BOMB_TYPE_CONVENTIONAL = 'CONVENTIONAL'
BOMB_TYPE_SMART = 'SMART'
BOMB_TYPE_NOVA = 'NOVA'
BOMB_TYPE_CHOICES = [
    (BOMB_TYPE_CONVENTIONAL, 'Conventional'),
    (BOMB_TYPE_SMART, 'Smart'),
    (BOMB_TYPE_NOVA, 'Nova'),
]

MINER_TYPE_SMALL = 'SMALL'
MINER_TYPE_MEDIUM = 'MEDIUM'
MINER_TYPE_LARGE = 'LARGE'
MINER_TYPE_CHOICES = [
    (MINER_TYPE_SMALL, 'Small'),
    (MINER_TYPE_MEDIUM, 'Medium'),
    (MINER_TYPE_LARGE, 'Large'),
]


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
        return HabitabilityRules.from_source(self).hab_min(env)

    def hab_max(self, env):
        """Get maximum habitable value for an environmental factor."""
        return HabitabilityRules.from_source(self).hab_max(env)

    def habitability_width_cost(self):
        """Total width points spent."""
        return HabitabilityRules.from_source(self).width_cost()

    def habitability_center_cost(self):
        """Total center points spent (average centers cost more)."""
        return HabitabilityRules.from_source(self).center_cost()

    def habitability_total_cost(self):
        """Total habitability points spent."""
        return HabitabilityRules.from_source(self).total_cost()

    def validate_habitability(self):
        """Validate habitability configuration. Returns list of errors."""
        return HabitabilityRules.from_source(self, budget=self.HABITABILITY_BUDGET).validate()

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
    value = models.CharField(max_length=30, blank=True, default='')
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
    email_game_updates = models.BooleanField(default=True)
    email_game_rollups_per_day = models.IntegerField(default=1)
    email_newsletter = models.BooleanField(default=True)
    email_unsubscribe_key = models.CharField(max_length=64, blank=True, default='')
    theme = models.CharField(max_length=20, choices=THEME_CHOICES, default='classic')
    website_url = models.URLField(blank=True, default='')
    discovered_resource_x = models.BooleanField(default=False)
    discovered_resource_y = models.BooleanField(default=False)
    discovered_resource_z = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.alias:
            self.alias = self.django_user.username
        if not self.email_unsubscribe_key:
            self.email_unsubscribe_key = uuid.uuid4().hex
        super(Account, self).save(*args, **kwargs)

    def __str__(self):
        if self.pk:
            return '%i:%s' % (self.pk, self.alias)
        return self.alias or '(new account)'


class EmailRollupLog(models.Model):
    """Record of sent message rollup emails."""
    account = models.ForeignKey(
        Account, related_name='email_rollups', on_delete=models.CASCADE
    )
    player = models.ForeignKey(
        'Player', related_name='email_rollups', on_delete=models.CASCADE
    )
    game = models.ForeignKey(
        'Game', related_name='email_rollups', on_delete=models.CASCADE
    )
    year = models.IntegerField(default=0)
    sent_at = models.DateTimeField(auto_now_add=True)
    message_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return '%s rollup %s @ %s' % (self.account.alias, self.game_id, self.sent_at)


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
    anomalies_enabled = models.BooleanField(default=False)
    no_scanners = models.BooleanField(default=False)
    max_starting_tech_level = models.IntegerField(default=5)
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
        return (
            self.stars.filter(x=x, y=y).first()
            or self.fleets.filter(x=x, y=y).first()
            or self.salvages.filter(x=x, y=y).first()
            or self.anomalys.filter(x=x, y=y).first()
            or None
        )

    def get_all_objects_at(self, x, y):
        return list(chain(
            self.stars.filter(x=x, y=y).all(),
            self.fleets.filter(x=x, y=y).all(),
            self.salvages.filter(x=x, y=y).all(),
            self.anomalys.filter(x=x, y=y).all(),
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
    resource_x_inventory = models.IntegerField(default=0)
    resource_y_inventory = models.IntegerField(default=0)
    resource_z_inventory = models.IntegerField(default=0)

    @property
    def total_minerals(self):
        """Total minerals in this salvage pile."""
        return (self.ironium_inventory + self.boranium_inventory +
                self.germanium_inventory + self.resource_x_inventory +
                self.resource_y_inventory + self.resource_z_inventory)

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


class Anomaly(AbstractMapObject):
    """Non-standard map object used for anomalies/events."""
    TYPE_NEBULA = 'NEBULA'
    TYPE_COMET = 'COMET'
    TYPE_RIFT = 'RIFT'
    TYPE_BLACK_HOLE = 'BLACK_HOLE'
    TYPE_WORMHOLE = 'WORMHOLE'
    TYPE_ANOMALY = 'ANOMALY'
    TYPE_CHOICES = [
        (TYPE_NEBULA, 'Nebula'),
        (TYPE_COMET, 'Comet'),
        (TYPE_RIFT, 'Rift'),
        (TYPE_BLACK_HOLE, 'Black Hole'),
        (TYPE_WORMHOLE, 'Wormhole'),
        (TYPE_ANOMALY, 'Anomaly'),
    ]

    name = models.CharField(max_length=30)
    description = models.TextField(blank=True, default='')
    anomaly_type = models.CharField(
        max_length=24, choices=TYPE_CHOICES, blank=True, default=TYPE_ANOMALY
    )
    # Heading in degrees: 0 = north, 90 = east, 180 = south, 270 = west
    heading = models.FloatField(default=random_heading_init)
    stability = models.IntegerField(
        default=random_anomaly_stability_init,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    wormhole_pair = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='wormhole_pair_reverse',
    )

    @property
    def player(self):
        return None


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
    resource_x_inventory = models.IntegerField(default=0)  # Secret resource X cargo in kt
    resource_y_inventory = models.IntegerField(default=0)  # Secret resource Y cargo in kt
    resource_z_inventory = models.IntegerField(default=0)  # Secret resource Z cargo in kt
    colonists = models.IntegerField(default=0)  # Current colonist cargo in thousands
    dry_mass = models.IntegerField(default=100)  # Dry mass in kt for colonise bonus
    max_safe_warp = models.IntegerField(default=2)
    fuel = models.FloatField(default=50.0)  # Current fuel in mg
    max_fuel = models.FloatField(default=50.0)  # Maximum fuel in mg
    fuel_efficiency = models.FloatField(default=1.0)  # Per-fleet fuel efficiency multiplier
    overmax_fuel_penalty = models.FloatField(default=1.0)  # Exponential burn multiplier above safe warp
    wormhole_fuel_per_ly = models.FloatField(default=5.0)
    wormhole_destruction_chance = models.FloatField(default=0.10)
    offense_level = models.FloatField(default=0.0)
    defense_level = models.FloatField(default=0.0)
    has_bombs = models.CharField(max_length=16, choices=BOMB_TYPE_CHOICES,
                                 null=True, blank=True, default=None)
    has_miners = models.CharField(max_length=16, choices=MINER_TYPE_CHOICES,
                                  null=True, blank=True, default=None)
    has_fuel_factory = models.BooleanField(default=False)
    has_wormhole_drive = models.BooleanField(default=False)
    basic_scanner_range = models.IntegerField(default=0)
    advanced_scanner_range = models.IntegerField(default=0)
    thumbnail_path = models.CharField(max_length=255, blank=True, default='')
    integrity = models.IntegerField(default=100,
            validators=[MinValueValidator(0), MaxValueValidator(100)])

    @staticmethod
    def _normalize_choice_or_none(value, allowed_values):
        if value in (None, False, '', 'False', 'false', 'NONE', 'none'):
            return None
        normalised = str(value).strip().upper()
        if normalised in allowed_values:
            return normalised
        return None

    def save(self, *args, **kwargs):
        self.has_bombs = self._normalize_choice_or_none(
            self.has_bombs,
            {choice for choice, _label in BOMB_TYPE_CHOICES},
        )
        self.has_miners = self._normalize_choice_or_none(
            self.has_miners,
            {choice for choice, _label in MINER_TYPE_CHOICES},
        )
        if not self.thumbnail_path:
            self.thumbnail_path = choose_fleet_thumbnail(self.id or self.short_id or self.name)
        try:
            basic = int(self.basic_scanner_range or 0)
        except (TypeError, ValueError):
            basic = 0
        try:
            advanced = int(self.advanced_scanner_range or 0)
        except (TypeError, ValueError):
            advanced = 0
        if advanced > basic:
            basic = advanced
        self.basic_scanner_range = max(0, basic)
        self.advanced_scanner_range = max(0, advanced)
        super(Fleet, self).save(*args, **kwargs)

    @property
    def effective_thumbnail_path(self):
        if self.thumbnail_path:
            return self.thumbnail_path
        return choose_fleet_thumbnail(self.id or self.short_id or self.name)

    @property
    def cargo_used(self):
        """Total cargo currently loaded (in kt equivalent)."""
        return (self.ironium_inventory + self.boranium_inventory +
                self.germanium_inventory + self.resource_x_inventory +
                self.resource_y_inventory + self.resource_z_inventory +
                self.colonists)

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
    resource_x_yield = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    resource_y_yield = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    resource_z_yield = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])

    # Surface mineral inventory (kt)
    ironium_inventory = models.IntegerField(default=random_surface_ironium_init)
    boranium_inventory = models.IntegerField(default=random_surface_boranium_init)
    germanium_inventory = models.IntegerField(default=random_surface_germanium_init)
    resource_x_inventory = models.IntegerField(default=0)
    resource_y_inventory = models.IntegerField(default=0)
    resource_z_inventory = models.IntegerField(default=0)

    colonists = models.IntegerField(default=0)
    # Base carrying capacity (in millions), scaled by nonlinear habitability.
    base_capacity = models.IntegerField(default=random_capacity_init)

    # Economic infrastructure
    mines = models.IntegerField(default=0)
    factories = models.IntegerField(default=0)
    labs = models.IntegerField(default=0)
    defenses = models.IntegerField(default=0)
    shipyards = models.IntegerField(default=0)
    buildpoints_consumed = models.IntegerField(default=0)  # Reset each turn

    @property
    def effective_thumbnail_path(self):
        return choose_star_thumbnail(self.id or self.short_id or self.name)


class ServerRace(UUIDMixin, HabitabilityMixin):
    name = models.CharField(max_length=16)
    plural_name = models.CharField(max_length=16)
    homeworld_name = models.CharField(max_length=30, blank=True, default='')
    starting_colonists = models.IntegerField(default=20)
    starting_mines = models.IntegerField(default=4)
    starting_factories = models.IntegerField(default=2)
    starting_labs = models.IntegerField(default=1)
    starting_shipyards = models.IntegerField(default=1)
    starting_fleets = models.IntegerField(default=2)
    starting_tech_level = models.IntegerField(default=3)
    convert_unused_buildpoints_to_research = models.BooleanField(default=False)
    singular_research = models.BooleanField(default=False)
    spend_leftover_points_on_research = models.BooleanField(default=False)
    leftover_points = models.FloatField(default=0.0)
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
    starting_colonists = models.IntegerField(default=20)
    starting_mines = models.IntegerField(default=4)
    starting_factories = models.IntegerField(default=2)
    starting_labs = models.IntegerField(default=1)
    starting_shipyards = models.IntegerField(default=1)
    starting_fleets = models.IntegerField(default=2)
    starting_tech_level = models.IntegerField(default=3)
    convert_unused_buildpoints_to_research = models.BooleanField(default=False)
    singular_research = models.BooleanField(default=False)
    spend_leftover_points_on_research = models.BooleanField(default=False)
    leftover_points = models.FloatField(default=0.0)
    turned_in = models.BooleanField(default=False)
    last_seen_year = models.IntegerField(null=True, blank=True)
    messages_seen_year = models.IntegerField(null=True, blank=True)
    discovered_resource_x = models.BooleanField(default=False)
    discovered_resource_y = models.BooleanField(default=False)
    discovered_resource_z = models.BooleanField(default=False)

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
        ('BOMB', 'Bomb'),
        ('REMOTEMINE', 'Remote Mine'),
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
                                     validators=[MinValueValidator(0), MaxValueValidator(14)])
    x = models.IntegerField(null=True)
    y = models.IntegerField(null=True)
    TARGET_KIND_CHOICES = [
        ('OBJECT', 'Object'),
        ('SPACE', 'Space'),
    ]
    target_kind = models.CharField(
        max_length=10, choices=TARGET_KIND_CHOICES, null=True, blank=True
    )
    target_short_id = models.CharField(max_length=12, null=True, blank=True, db_index=True)
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
    transfer_resource_x = models.IntegerField(default=0)
    transfer_resource_y = models.IntegerField(default=0)
    transfer_resource_z = models.IntegerField(default=0)
    transfer_colonists = models.IntegerField(default=0)

    # Patrol parameters
    patrol_radius = models.IntegerField(default=0)
    intercept_speed = models.IntegerField(default=5)

    # Bombing/remotemining completion parameters
    BOMB_UNTIL_CHOICES = [
        ('COLONISTS_ZERO', 'Until Zero Colonists'),
        ('DEFENSES_ZERO', 'Until Zero Defenses'),
        ('ONCE', 'Once'),
    ]
    bomb_until = models.CharField(
        max_length=20,
        choices=BOMB_UNTIL_CHOICES,
        default='COLONISTS_ZERO',
    )
    mine_until_full = models.BooleanField(default=True)
    remotemine_focus = models.TextField(blank=True, default='')

    @property
    def target(self):
        """Return a string description of the order target."""
        obj, x, y, kind = self.get_actual_target()
        if kind == 'star' and obj:
            return obj.name
        elif kind == 'fleet' and obj:
            return f"Fleet {obj.name}"
        elif kind == 'salvage' and obj:
            return f"Salvage ({obj.x}, {obj.y})"
        elif kind == 'space' and x is not None and y is not None:
            return f"({self.x}, {self.y})"
        else:
            return "Unknown destination"

    def target_is_star(self):
        _obj, _x, _y, kind = self.get_actual_target()
        return kind == 'star'

    def target_is_fleet(self):
        _obj, _x, _y, kind = self.get_actual_target()
        return kind == 'fleet'

    def target_is_salvage(self):
        _obj, _x, _y, kind = self.get_actual_target()
        return kind == 'salvage'

    def has_target_coordinates(self):
        return self.x is not None and self.y is not None

    def get_actual_target(self):
        """Return canonical target and coordinates.

        Prefers explicit target objects when present and valid, otherwise falls
        back to explicit x/y coordinates. Returns (obj, x, y, kind).
        """
        if (self.target_kind or '').upper() == 'SPACE':
            if self.has_target_coordinates():
                return None, self.x, self.y, 'space'
            return None, None, None, 'none'

        if self.target_short_id:
            short_id = str(self.target_short_id).strip().lower()
            if short_id:
                obj = (
                    Star.objects.filter(game=self.game, short_id=short_id).first()
                    or Fleet.objects.filter(game=self.game, short_id=short_id).first()
                    or Salvage.objects.filter(game=self.game, short_id=short_id).first()
                    or Anomaly.objects.filter(game=self.game, short_id=short_id).first()
                )
                if obj is not None:
                    if isinstance(obj, Star):
                        return obj, obj.x, obj.y, 'star'
                    if isinstance(obj, Fleet):
                        return obj, obj.x, obj.y, 'fleet'
                    if isinstance(obj, Salvage):
                        return obj, obj.x, obj.y, 'salvage'
                    return obj, obj.x, obj.y, 'anomaly'
            if self.has_target_coordinates():
                return None, self.x, self.y, 'space'
            return None, None, None, 'none'

        if self.target_star_id:
            try:
                obj = self.target_star
                if obj is None:
                    raise Star.DoesNotExist()
                return obj, obj.x, obj.y, 'star'
            except Star.DoesNotExist:
                if self.has_target_coordinates():
                    return None, self.x, self.y, 'space'
                return None, None, None, 'none'
        if self.target_fleet_id:
            try:
                obj = self.target_fleet
                if obj is None:
                    raise Fleet.DoesNotExist()
                return obj, obj.x, obj.y, 'fleet'
            except Fleet.DoesNotExist:
                if self.has_target_coordinates():
                    return None, self.x, self.y, 'space'
                return None, None, None, 'none'
        if self.target_salvage_id:
            try:
                obj = self.target_salvage
                if obj is None:
                    raise Salvage.DoesNotExist()
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
        obj, x, y, kind = self.get_actual_target()
        if kind in ['star', 'fleet', 'salvage'] and obj:
            return obj.x, obj.y
        if kind == 'space' and x is not None and y is not None:
            return x, y
        raise ValueError(f"Invalid order {self.id} - no valid destination")

    def save(self, *args, **kwargs):
        if self.pk is None and (self.position is None or self.position == 0):
            max_pos = FleetOrders.objects.filter(
                fleet=self.fleet
            ).aggregate(models.Max('position'))['position__max'] or 0
            self.position = max_pos + 1
        super(FleetOrders, self).save(*args, **kwargs)


class ResearchCategory(models.Model):
    """Research category with configurable display order."""
    code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=32)
    description = models.TextField(blank=True, default='')
    metadata_json = models.TextField(default='{}')
    display_order = models.IntegerField(default=0)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name_plural = 'Research categories'

    def __str__(self):
        return self.name


class Technology(UUIDMixin):
    """A research unlock associated with category + level."""
    TECH_TYPE_CHOICES = [
        ('PROPULSION', 'Propulsion'),
        ('HULL', 'Hull'),
        ('ENERGY_WEAPON', 'Energy Weapon'),
        ('TORPEDO', 'Torpedo'),
        ('SHIELD', 'Shield'),
        ('ARMOUR', 'Armour'),
        ('SCANNER', 'Scanner'),
        ('INFRASTRUCTURE', 'Infrastructure'),
        ('ELECTRICAL', 'Electrical'),
        ('MECHANICAL', 'Mechanical'),
        ('BOMB', 'Bomb'),
        ('OTHER', 'Other'),
    ]

    category = models.ForeignKey(
        ResearchCategory, related_name='technologies', on_delete=models.CASCADE
    )
    level = models.IntegerField(default=0)
    name = models.CharField(max_length=64)
    description = models.TextField(blank=True, default='')
    tech_type = models.CharField(
        max_length=16, choices=TECH_TYPE_CHOICES, default='OTHER'
    )
    params_json = models.TextField(default='{}')
    display_order = models.IntegerField(default=0)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ['category', 'level', 'display_order', 'name']
        unique_together = [['category', 'level', 'name']]

    def __str__(self):
        return '%s L%s: %s' % (self.category.name, self.level, self.name)


class HullDesign(models.Model):
    """Staff-authored hull blueprint prototype (no gameplay integration yet)."""
    name = models.CharField(max_length=64, unique=True)
    thumbnail_class = models.CharField(max_length=32, blank=True, default='scout')
    offense_offset = models.FloatField(default=0.0)
    defense_offset = models.FloatField(default=0.0)
    ironium_cost = models.IntegerField(default=0)
    boranium_cost = models.IntegerField(default=0)
    germanium_cost = models.IntegerField(default=0)
    resource_x_cost = models.IntegerField(default=0)
    resource_y_cost = models.IntegerField(default=0)
    resource_z_cost = models.IntegerField(default=0)
    cargo_capacity = models.IntegerField(default=0)
    fuel_capacity = models.IntegerField(default=100)
    cargo_hold_grid_width = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(24)])
    cargo_hold_grid_height = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(24)])
    grid_columns = models.IntegerField(default=8, validators=[MinValueValidator(1), MaxValueValidator(24)])
    grid_rows = models.IntegerField(default=8, validators=[MinValueValidator(1), MaxValueValidator(24)])
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def clean(self):
        super(HullDesign, self).clean()
        hold_w = int(self.cargo_hold_grid_width or 0)
        hold_h = int(self.cargo_hold_grid_height or 0)
        if (hold_w == 0) != (hold_h == 0):
            raise ValidationError('Set both cargo hold width and height to 0 to disable cargo hold.')
        if hold_w > int(self.grid_columns or 1):
            raise ValidationError('Cargo hold width cannot exceed hull grid columns.')
        if hold_h > int(self.grid_rows or 1):
            raise ValidationError('Cargo hold height cannot exceed hull grid rows.')

    @property
    def subgrid_columns(self):
        return int(self.grid_columns) * 2

    @property
    def subgrid_rows(self):
        return int(self.grid_rows) * 2


class HullDesignSlot(models.Model):
    """A 2x2 subgrid slot placed within a hull blueprint."""
    SLOT_TECH_TYPE_CHOICES = [
        ('ANY', 'Any'),
        ('MISC', 'Misc'),
        ('ANY_WEAPON', 'Any Weapon'),
        ('SHIELD_OR_ARMOUR', 'Shield or Armour'),
        ('PROPULSION', 'Propulsion'),
        ('HULL', 'Hull'),
        ('ENERGY_WEAPON', 'Energy Weapon'),
        ('TORPEDO', 'Torpedo'),
        ('SHIELD', 'Shield'),
        ('ARMOUR', 'Armour'),
        ('INFRASTRUCTURE', 'Infrastructure'),
        ('ELECTRICAL', 'Electrical'),
        ('MECHANICAL', 'Mechanical'),
        ('OTHER', 'Other'),
    ]

    hull = models.ForeignKey(HullDesign, related_name='slots', on_delete=models.CASCADE)
    # Top-left anchor in the doubled subgrid coordinate system.
    x = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    y = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    tech_type = models.CharField(max_length=16, choices=SLOT_TECH_TYPE_CHOICES, default='OTHER')
    item_count = models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(99)])
    max_tech_level = models.IntegerField(default=5, validators=[MinValueValidator(0), MaxValueValidator(99)])
    display_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'id']
        unique_together = [['hull', 'x', 'y']]

    def __str__(self):
        return '%s slot (%s,%s)' % (self.hull.name, self.x, self.y)

    def clean(self):
        if self.hull_id is None:
            return

        max_x = self.hull.subgrid_columns - 2
        max_y = self.hull.subgrid_rows - 2
        if self.x < 0 or self.y < 0 or self.x > max_x or self.y > max_y:
            raise ValidationError('Slot position is outside hull grid bounds.')

        # Slots occupy 2x2 in subgrid coordinates; prevent overlaps.
        existing = HullDesignSlot.objects.filter(hull=self.hull)
        if self.pk:
            existing = existing.exclude(pk=self.pk)
        for other in existing:
            if (self.x < other.x + 2 and self.x + 2 > other.x and
                    self.y < other.y + 2 and self.y + 2 > other.y):
                raise ValidationError('Slot overlaps an existing slot.')


class PlayerResearch(models.Model):
    """Per-player progress and allocation for each research category."""
    player = models.ForeignKey(
        Player, related_name='research_progress', on_delete=models.CASCADE
    )
    category = models.ForeignKey(
        ResearchCategory, related_name='player_progress', on_delete=models.CASCADE
    )
    current_level = models.FloatField(default=0.0)
    stored_rp = models.FloatField(default=0.0)
    allocation_percent = models.FloatField(default=25.0)
    ironium_paid = models.IntegerField(default=0)
    boranium_paid = models.IntegerField(default=0)
    germanium_paid = models.IntegerField(default=0)
    resource_x_paid = models.IntegerField(default=0)
    resource_y_paid = models.IntegerField(default=0)
    resource_z_paid = models.IntegerField(default=0)

    class Meta:
        unique_together = [['player', 'category']]
        ordering = ['category', 'player']

    def __str__(self):
        return '%s %s' % (self.player.name, self.category.name)


class DefaultResearchLevelRequirement(models.Model):
    """Default per-level research requirements used to seed categories."""
    level = models.IntegerField(unique=True)
    rp_cost = models.IntegerField(default=0)
    ironium_cost = models.IntegerField(default=0)
    boranium_cost = models.IntegerField(default=0)
    germanium_cost = models.IntegerField(default=0)
    resource_x_cost = models.IntegerField(default=0)
    resource_y_cost = models.IntegerField(default=0)
    resource_z_cost = models.IntegerField(default=0)

    class Meta:
        ordering = ['level']

    def __str__(self):
        return 'L%s default' % self.level


class ResearchLevelRequirement(models.Model):
    """Per-category per-level research requirements."""
    category = models.ForeignKey(
        ResearchCategory, related_name='level_requirements',
        on_delete=models.CASCADE
    )
    level = models.IntegerField()
    rp_cost = models.IntegerField(default=0)
    ironium_cost = models.IntegerField(default=0)
    boranium_cost = models.IntegerField(default=0)
    germanium_cost = models.IntegerField(default=0)
    resource_x_cost = models.IntegerField(default=0)
    resource_y_cost = models.IntegerField(default=0)
    resource_z_cost = models.IntegerField(default=0)

    class Meta:
        unique_together = [['category', 'level']]
        ordering = ['category', 'level']

    def __str__(self):
        return '%s L%s' % (self.category.name, self.level)


class ResearchLevelPrerequisite(models.Model):
    """Per-category cross-category prerequisites for research levels."""
    category = models.ForeignKey(
        ResearchCategory, related_name='level_prerequisites',
        on_delete=models.CASCADE
    )
    level = models.IntegerField()
    requires_category = models.ForeignKey(
        ResearchCategory, related_name='required_by_levels',
        on_delete=models.CASCADE
    )
    min_level = models.IntegerField(default=0)

    class Meta:
        unique_together = [['category', 'level', 'requires_category']]
        ordering = ['category', 'level', 'requires_category']

    def __str__(self):
        return '%s L%s requires %s L%s' % (
            self.category.name,
            self.level,
            self.requires_category.name,
            self.min_level,
        )


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
    'BUILD_LAB': {'bp': 20, 'ironium': 50, 'boranium': 20, 'germanium': 20, 'colonists': 0},
    'BUILD_DEFENSE': {'bp': 50, 'ironium': 100, 'boranium': 50, 'germanium': 50, 'colonists': 0},
    'BUILD_SHIPYARD': {'bp': 100, 'ironium': 250, 'boranium': 50, 'germanium': 100,
                       'colonists': 0},
    'BUILD_FLEET': {'bp': 50, 'ironium': 100, 'boranium': 200, 'germanium': 200, 'colonists': 0},
    'TERRAFORM_GRAVITY': {'bp': 100, 'ironium': 750, 'boranium': 150, 'germanium': 100, 'colonists': 0},
    'TERRAFORM_TEMPERATURE': {'bp': 100, 'ironium': 200, 'boranium': 660, 'germanium': 140, 'colonists': 0},
    'TERRAFORM_RADIATION': {'bp': 100, 'ironium': 50, 'boranium': 475, 'germanium': 475, 'colonists': 0},
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
        ('BUILD_LAB', 'Build Lab'),
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
    spent_resource_x = models.IntegerField(default=0)
    spent_resource_y = models.IntegerField(default=0)
    spent_resource_z = models.IntegerField(default=0)
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
        ('anomaly', 'Anomaly'),
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
