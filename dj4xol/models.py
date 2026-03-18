from django.db import models
from django.db.utils import IntegrityError
from django import forms
from django.contrib.auth import models as auth_models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.exceptions import ValidationError
from itertools import chain
from .starnamer import StarNamer
from .habitability_rules import HabitabilityRules
from .fleet_thumbnails import (
    choose_fleet_thumbnail,
    get_ship_class_from_path,
    is_valid_fleet_thumbnail,
)
from .star_thumbnails import choose_star_thumbnail, is_valid_star_thumbnail
from .anomaly_thumbnails import (
    choose_anomaly_thumbnail,
    choose_random_anomaly_thumbnail,
    is_valid_anomaly_thumbnail,
)
from .name_rules import (
    parse_profanity_terms,
    validate_non_reserved_identity_name,
    validate_safe_public_text,
)
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
    short_id = models.CharField(max_length=12, editable=False)

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


def server_setting_enabled(key, default=False):
    value = ServerSettings.get(key, 'True' if default else 'False')
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def server_setting_int(key, default=0):
    value = ServerSettings.get(key, str(default))
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return int(default)


def profanity_filter_settings():
    return {
        'enabled': server_setting_enabled('enable_profanity_filter', True),
        'whitelist': parse_profanity_terms(ServerSettings.get('profanity_filter_whitelist', '')),
        'blacklist': parse_profanity_terms(ServerSettings.get('profanity_filter_blacklist', '')),
    }


class CustomHelpPage(models.Model):
    slug = models.SlugField(max_length=60, unique=True)
    title = models.CharField(max_length=120)
    tagline = models.CharField(max_length=120, blank=True, default='')
    summary = models.CharField(max_length=255, blank=True, default='')
    nav_order = models.IntegerField(default=100)
    published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nav_order', 'title', 'id']

    def __str__(self):
        return '%s' % (self.title or self.slug)


class CustomHelpPageBlock(models.Model):
    page = models.ForeignKey(
        CustomHelpPage,
        related_name='blocks',
        on_delete=models.CASCADE,
    )
    display_order = models.IntegerField(default=10)
    heading = models.CharField(max_length=120, blank=True, default='')
    body = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['display_order', 'id']

    def __str__(self):
        heading = self.heading or 'Block'
        return '%s: %s' % (self.page.title, heading)


class Account(models.Model):
    """A dj4xol account linked to a Django user."""
    THEME_CHOICES = [
        ('classic', 'Classic'),
        ('lcars', 'LCARS'),
        ('win95', 'Windows 95'),
    ]
    ONBOARDING_STEP_COMPLETE = 'COMPLETE'
    ONBOARDING_STEP_THEME = 'THEME'
    ONBOARDING_STEP_RACE = 'RACE'
    ONBOARDING_STEP_CHOICES = [
        (ONBOARDING_STEP_COMPLETE, 'Complete'),
        (ONBOARDING_STEP_THEME, 'Theme'),
        (ONBOARDING_STEP_RACE, 'Race'),
    ]

    django_user = models.OneToOneField(auth_models.User, primary_key=True,
            related_name="dj4xol_account", on_delete=models.PROTECT)
    full_name = models.CharField(max_length=60)
    alias = models.CharField(max_length=30, unique=True)
    email = models.EmailField()
    email_game_updates = models.BooleanField(default=True)
    email_game_rollups_per_day = models.IntegerField(default=1)
    email_newsletter = models.BooleanField(default=True)
    email_verified = models.BooleanField(default=False)
    email_verification_key = models.CharField(max_length=64, blank=True, default='')
    email_unsubscribe_key = models.CharField(max_length=64, blank=True, default='')
    theme = models.CharField(max_length=20, choices=THEME_CHOICES, default='classic')
    onboarding_step = models.CharField(
        max_length=12,
        choices=ONBOARDING_STEP_CHOICES,
        default=ONBOARDING_STEP_COMPLETE,
    )
    website_url = models.URLField(blank=True, default='')
    discovered_resource_x = models.BooleanField(default=False)
    discovered_resource_y = models.BooleanField(default=False)
    discovered_resource_z = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        profanity_filter = profanity_filter_settings()
        if not self.alias:
            self.alias = self.django_user.username
        validate_non_reserved_identity_name(
            self.alias,
            'Account name',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )
        self.full_name = validate_safe_public_text(
            self.full_name,
            'Full name',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )
        if not self.email_verification_key:
            self.email_verification_key = uuid.uuid4().hex
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
    ANOMALY_SPAWN_RATE_CHOICES = [
        ('LOW', 'Low'),
        ('NORMAL', 'Normal'),
        ('HIGH', 'High'),
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
    anomaly_spawn_rate = models.CharField(
        max_length=10,
        choices=ANOMALY_SPAWN_RATE_CHOICES,
        default='NORMAL',
    )
    research_cost_multiplier = models.FloatField(default=1.0)
    warp_speed_multiplier = models.FloatField(default=1.0)
    no_scanners = models.BooleanField(default=False)
    max_starting_tech_level = models.IntegerField(default=5)
    last_generated = models.DateTimeField(null=True, blank=True)
    next_generation = models.DateTimeField(null=True, blank=True)
    is_generating = models.BooleanField(default=False)

    _star_names = []
    _star_namer = None

    class Meta:
        unique_together = [['short_id']]

    def __str__(self):
        return f'{self.short_id} {self.name}'

    def save(self, *args, **kwargs):
        profanity_filter = profanity_filter_settings()
        self.name = validate_safe_public_text(
            self.name,
            'Game name',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )
        self.description = validate_safe_public_text(
            self.description,
            'Game description',
            allow_newlines=True,
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )
        super(Game, self).save(*args, **kwargs)

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


def _base36_chars():
    import string
    return string.digits + string.ascii_lowercase


def _int_to_base36(value, width):
    chars = _base36_chars()
    if value < 0:
        value = -value
    out = ''
    temp = int(value)
    for _ in range(width):
        out = chars[temp % 36] + out
        temp //= 36
    return out or '0'.rjust(width, '0')


def build_game_short_id(game_short_id, uuid_int):
    """Generate a 12-char game-scoped short id from a UUID int."""
    # XOR the 128-bit UUID in 32-bit chunks to get 32 bits
    chunk1 = (uuid_int >> 96) & 0xFFFFFFFF  # Top 32 bits
    chunk2 = (uuid_int >> 64) & 0xFFFFFFFF  # Next 32 bits
    chunk3 = (uuid_int >> 32) & 0xFFFFFFFF  # Next 32 bits
    chunk4 = uuid_int & 0xFFFFFFFF          # Bottom 32 bits

    xor_result = chunk1 ^ chunk2 ^ chunk3 ^ chunk4
    short_part = _int_to_base36(xor_result, 8)
    return f"{(game_short_id or '')[:4]}{short_part}"


def iter_short_id_suffixes(max_len=3):
    """Yield deterministic base36 suffixes for collision resolution."""
    for length in range(1, max_len + 1):
        for counter in range(36 ** length):
            yield _int_to_base36(counter, length)


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
            base = self._generate_short_id_from_uuid(uuid_int)
            self.short_id = self._resolve_game_short_id_collision(base)

        super(UUIDMixin, self).save(*args, **kwargs)

    def _generate_short_id_from_uuid(self, uuid_int):
        """Generate base short_id by XORing UUID chunks."""
        return build_game_short_id(self.game.short_id, uuid_int)

    def _short_id_in_use(self, candidate):
        """Check if candidate short_id is already used within this game."""
        if not self.game_id:
            return False
        if isinstance(self, AbstractMapObject):
            model_candidates = [Star, Fleet, Salvage, Anomaly]
        else:
            model_candidates = [self.__class__]
        for model in model_candidates:
            qs = model.objects.filter(game_id=self.game_id, short_id=candidate)
            if self.pk and model == self.__class__:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                return True
        return False

    def _resolve_game_short_id_collision(self, base):
        if not self._short_id_in_use(base):
            return base
        for suffix in iter_short_id_suffixes():
            candidate = f"{base[:12 - len(suffix)]}{suffix}"
            if not self._short_id_in_use(candidate):
                return candidate
        return base

    class Meta:
        abstract = True


class AbstractMapObject(AbstractGameObject):
    x = models.IntegerField()
    y = models.IntegerField()

    class Meta:
        abstract = True


class ServerRaceType(models.Model):
    code = models.CharField(max_length=4, primary_key=True, unique=True)
    display_order = models.IntegerField(default=100)
    name = models.CharField(max_length=16)
    enabled = models.BooleanField(default=True)
    description = models.TextField()
    starting_colonies = models.IntegerField(default=1)
    starting_planet_has_stargate = models.BooleanField(default=False)
    population_growth_multiplier = models.FloatField(default=1.0)
    population_growth_uses_resources = models.BooleanField(default=False)
    population_cap_multiplier = models.IntegerField(default=1)
    race_creation_points_balance = models.FloatField(default=0.0)
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
    warp_advantage = models.FloatField(default=0.0)
    stealth_multiplier = models.FloatField(default=1.0)
    terraforming_multiplier = models.FloatField(default=1.0)
    political_stability = models.FloatField(default=1.0)
    luck_multiplier = models.FloatField(default=1.0)
    ignores_radiation = models.BooleanField(default=False)
    ignores_temperature = models.BooleanField(default=False)
    ignores_gravity = models.BooleanField(default=False)
    has_no_terraforming = models.BooleanField(default=False)
    only_basic_terraforming = models.BooleanField(default=False)
    has_advanced_mines = models.BooleanField(default=False)
    has_advanced_stargates = models.BooleanField(default=False)
    has_advanced_remoteminers = models.BooleanField(default=False)
    has_advanced_hulls = models.BooleanField(default=False)
    has_superweapon = models.BooleanField(default=False)
    has_bombs = models.BooleanField(default=True)
    has_metalurgy = models.BooleanField(default=True)
    has_no_stealth = models.BooleanField(default=False)
    has_generalised_research = models.BooleanField(default=False)
    is_parasitic = models.BooleanField(default=False)
    is_cybernetic = models.BooleanField(default=False)
    is_mechanical = models.BooleanField(default=False)
    is_energy_being = models.BooleanField(default=False)
    research_multiplier = models.FloatField(default=1.0)
    initiative_multiplier = models.FloatField(default=1.0)
    cargo_multiplier = models.FloatField(default=1.0)

    def __str__(self):
        return self.name


class Salvage(AbstractMapObject):
    """Recoverable minerals left behind when vessels are destroyed or scuttled."""
    TYPE_SALVAGE = 'SALVAGE'
    TYPE_ASTEROID_FIELD = 'ASTEROID_FIELD'
    TYPE_ANCIENT_DEBRIS = 'ANCIENT_DEBRIS'
    TYPE_CHOICES = [
        (TYPE_SALVAGE, 'Salvage'),
        (TYPE_ASTEROID_FIELD, 'Asteroid Field'),
        (TYPE_ANCIENT_DEBRIS, 'Ancient Debris'),
    ]

    salvage_type = models.CharField(
        max_length=24,
        choices=TYPE_CHOICES,
        default=TYPE_SALVAGE,
    )
    danger_level = models.CharField(max_length=12, blank=True, default='')
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
        if self.salvage_type == self.TYPE_ASTEROID_FIELD:
            return f"Asteroid Field ({self.x}, {self.y})"
        if self.salvage_type == self.TYPE_ANCIENT_DEBRIS:
            return f"Ancient Debris ({self.x}, {self.y})"
        return f"Salvage ({self.x}, {self.y})"

    @property
    def player(self):
        """Salvage is neutral - no owner."""
        return None

    class Meta:
        unique_together = [['game', 'x', 'y'], ['game', 'short_id']]


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
    thumbnail_path = models.CharField(max_length=255, blank=True, default='')

    @property
    def player(self):
        return None

    def save(self, *args, **kwargs):
        if not self.thumbnail_path or not is_valid_anomaly_thumbnail(self.thumbnail_path):
            self.thumbnail_path = choose_random_anomaly_thumbnail(self.anomaly_type)
        super(Anomaly, self).save(*args, **kwargs)

    @property
    def effective_thumbnail_path(self):
        if self.thumbnail_path and is_valid_anomaly_thumbnail(self.thumbnail_path):
            return self.thumbnail_path
        return choose_random_anomaly_thumbnail(self.anomaly_type) or choose_anomaly_thumbnail(
            self.id or self.short_id or self.name, self.anomaly_type
        )

    class Meta:
        unique_together = [['game', 'short_id']]


class Fleet(AbstractMapObject):
    """A group of ships traveling together."""
    name = models.CharField(max_length=30)
    player = models.ForeignKey('Player', related_name='fleets',
            on_delete=models.SET_NULL, null=True, default=None)
    # Heading in degrees: 0 = north, 90 = east, 180 = south, 270 = west
    heading = models.FloatField(default=0.0)
    # Effective warp actually traveled during the previous processed year.
    travel_warp = models.IntegerField(default=0)
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
    warp_advantage = models.FloatField(default=0.0)
    wormhole_fuel_per_ly = models.FloatField(default=5.0)
    wormhole_destruction_chance = models.FloatField(default=0.10)
    offense_level = models.FloatField(default=0.0)
    defense_level = models.FloatField(default=0.0)
    has_bombs = models.CharField(max_length=16, choices=BOMB_TYPE_CHOICES,
                                 null=True, blank=True, default=None)
    has_miners = models.CharField(max_length=16, choices=MINER_TYPE_CHOICES,
                                  null=True, blank=True, default=None)
    has_fuel_factory = models.BooleanField(default=False)
    fuel_factory_mg_per_year = models.FloatField(default=0.0)
    fuel_factory_max_warp = models.IntegerField(default=-1)
    has_wormhole_drive = models.BooleanField(default=False)
    max_cloaked_warp = models.IntegerField(default=-1)
    advanced_cloak = models.BooleanField(default=False)
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
        try:
            cloaked_warp = int(self.max_cloaked_warp or 0)
        except (TypeError, ValueError):
            cloaked_warp = 0
        try:
            fuel_factory_rate = float(self.fuel_factory_mg_per_year or 0.0)
        except (TypeError, ValueError):
            fuel_factory_rate = 0.0
        try:
            fuel_factory_max_warp = int(self.fuel_factory_max_warp)
        except (TypeError, ValueError):
            fuel_factory_max_warp = -1
        if fuel_factory_rate <= 0.0:
            fuel_factory_rate = 0.0
            fuel_factory_max_warp = -1
        elif fuel_factory_max_warp < 0:
            fuel_factory_max_warp = 0
        self.max_cloaked_warp = max(-1, cloaked_warp)
        self.fuel_factory_mg_per_year = fuel_factory_rate
        self.fuel_factory_max_warp = max(-1, fuel_factory_max_warp)
        self.has_fuel_factory = fuel_factory_rate > 0.0
        self.advanced_cloak = bool(self.advanced_cloak)
        self.basic_scanner_range = max(0, basic)
        self.advanced_scanner_range = max(0, advanced)
        super(Fleet, self).save(*args, **kwargs)

    @property
    def effective_thumbnail_path(self):
        if self.thumbnail_path and is_valid_fleet_thumbnail(self.thumbnail_path):
            return self.thumbnail_path
        ship_class = get_ship_class_from_path(self.thumbnail_path)
        return choose_fleet_thumbnail(self.id or self.short_id or self.name, ship_class)

    @property
    def owner_display_name(self):
        if self.player_id:
            alias = self.player.account.alias if getattr(self.player, 'account', None) else 'Unknown'
            return '%s (%s)' % (self.player.name, alias)
        return "Abandoned"

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

    class Meta:
        unique_together = [['game', 'short_id']]


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
    has_administration = models.BooleanField(default=False)
    buildpoints_consumed = models.IntegerField(default=0)  # Reset each turn
    thumbnail_path = models.CharField(max_length=255, blank=True, default='')

    def save(self, *args, **kwargs):
        if not self.thumbnail_path or not is_valid_star_thumbnail(self.thumbnail_path):
            self.thumbnail_path = choose_star_thumbnail(self.id or self.short_id or self.name)
        super(Star, self).save(*args, **kwargs)

    @property
    def effective_thumbnail_path(self):
        if self.thumbnail_path and is_valid_star_thumbnail(self.thumbnail_path):
            return self.thumbnail_path
        return choose_star_thumbnail(self.id or self.short_id or self.name)

    class Meta:
        unique_together = [['game', 'short_id']]


class ServerRace(UUIDMixin, HabitabilityMixin):
    name = models.CharField(max_length=16)
    plural_name = models.CharField(max_length=16)
    homeworld_name = models.CharField(max_length=30, blank=True, default='')
    fixed_homeworld = models.BooleanField(default=False)
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

    def save(self, *args, **kwargs):
        profanity_filter = profanity_filter_settings()
        self.name = validate_non_reserved_identity_name(
            self.name,
            'Race name',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )
        self.plural_name = validate_non_reserved_identity_name(
            self.plural_name,
            'Race plural name',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )
        self.homeworld_name = validate_non_reserved_identity_name(
            self.homeworld_name,
            'Homeworld name',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        ) if self.homeworld_name else self.homeworld_name
        self.description = validate_safe_public_text(
            self.description,
            'Race description',
            allow_newlines=True,
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )
        super(ServerRace, self).save(*args, **kwargs)

    class Meta:
        unique_together = [['short_id']]


class Player(AbstractGameObject, HabitabilityMixin):
    """A player instance in a game, with their chosen race."""
    STANCE_CHOICES = [
        ('HOSTILE', 'Hostile'),
        ('COLD', 'Cold'),
        ('NEUTRAL', 'Neutral'),
        ('WARM', 'Warm'),
        ('ALLIED', 'Allied'),
    ]

    account = models.ForeignKey(Account, related_name="players",
                                null=True, default=None,
                                on_delete=models.SET_NULL)
    name = models.CharField(max_length=16)
    plural_name = models.CharField(max_length=16, null=True, default=None)
    homeworld_name = models.CharField(max_length=30, blank=True, default='')
    homeworld = models.ForeignKey(Star, null=True, default=None,
                                  related_name="homeworld_of",
                                  on_delete=models.SET_NULL)
    fixed_homeworld = models.BooleanField(default=False)
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
    defeated = models.BooleanField(default=False)
    last_seen_year = models.IntegerField(null=True, blank=True)
    messages_seen_year = models.IntegerField(null=True, blank=True)
    discovered_resource_x = models.BooleanField(default=False)
    discovered_resource_y = models.BooleanField(default=False)
    discovered_resource_z = models.BooleanField(default=False)
    default_diplomatic_stance = models.CharField(
        max_length=8,
        choices=STANCE_CHOICES,
        default='NEUTRAL',
    )
    pending_default_diplomatic_stance = models.CharField(
        max_length=8,
        choices=STANCE_CHOICES,
        default='NEUTRAL',
    )

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if update_fields and 'default_diplomatic_stance' in update_fields and 'pending_default_diplomatic_stance' not in update_fields:
            self.pending_default_diplomatic_stance = self.default_diplomatic_stance
            kwargs['update_fields'] = list(set(update_fields) | {'pending_default_diplomatic_stance'})
        elif self._state.adding and self.pending_default_diplomatic_stance == 'NEUTRAL' and self.default_diplomatic_stance != 'NEUTRAL':
            self.pending_default_diplomatic_stance = self.default_diplomatic_stance
        profanity_filter = profanity_filter_settings()
        if self.plural_name is None:
            self.plural_name = self.name + 's'
        self.name = validate_non_reserved_identity_name(
            self.name,
            'Player name',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )
        self.plural_name = validate_non_reserved_identity_name(
            self.plural_name,
            'Player plural name',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )
        self.homeworld_name = validate_non_reserved_identity_name(
            self.homeworld_name,
            'Homeworld name',
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        ) if self.homeworld_name else self.homeworld_name
        self.description = validate_safe_public_text(
            self.description,
            'Player description',
            allow_newlines=True,
            block_profanity=profanity_filter['enabled'],
            profanity_whitelist=profanity_filter['whitelist'],
            profanity_blacklist=profanity_filter['blacklist'],
        )
        super(Player, self).save(*args, **kwargs)

    class Meta:
        unique_together = [['game', 'short_id']]


class PlayerNote(models.Model):
    """Player-authored notes for a specific game session."""
    player = models.ForeignKey(
        Player, related_name='notes', on_delete=models.CASCADE
    )
    note_id = models.IntegerField()
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['note_id']
        unique_together = [['player', 'note_id']]


class PlayerStarMarker(models.Model):
    """Per-player visual markers for stars on the starmap."""
    TYPE_CIRCLE = 'CIRCLE'
    TYPE_X = 'X'
    TYPE_CHOICES = [
        (TYPE_CIRCLE, 'Circle'),
        (TYPE_X, 'X'),
    ]
    COLOR_WHITE = 'WHITE'
    COLOR_RED = 'RED'
    COLOR_YELLOW = 'YELLOW'
    COLOR_GREEN = 'GREEN'
    COLOR_BLUE = 'BLUE'
    COLOR_INDIGO = 'INDIGO'
    COLOR_VIOLET = 'VIOLET'
    COLOR_CHOICES = [
        (COLOR_WHITE, 'White'),
        (COLOR_RED, 'Red'),
        (COLOR_YELLOW, 'Yellow'),
        (COLOR_GREEN, 'Green'),
        (COLOR_BLUE, 'Blue'),
        (COLOR_INDIGO, 'Indigo'),
        (COLOR_VIOLET, 'Violet'),
    ]
    COLOR_VALUES = {choice[0] for choice in COLOR_CHOICES}

    player = models.ForeignKey(
        Player, related_name='star_markers', on_delete=models.CASCADE
    )
    star = models.ForeignKey(
        Star, related_name='player_markers', on_delete=models.CASCADE
    )
    marker_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
    )
    marker_color = models.CharField(
        max_length=10,
        choices=COLOR_CHOICES,
        default=COLOR_WHITE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['player', 'star']]


class PlayerDiplomaticStance(models.Model):
    player = models.ForeignKey(
        Player, related_name='diplomatic_stances', on_delete=models.CASCADE
    )
    target_player = models.ForeignKey(
        Player, related_name='diplomatic_stances_targeted_by', on_delete=models.CASCADE
    )
    stance = models.CharField(
        max_length=8,
        choices=Player.STANCE_CHOICES,
        default='NEUTRAL',
    )
    pending_stance = models.CharField(
        max_length=8,
        choices=Player.STANCE_CHOICES,
        default='NEUTRAL',
    )
    reveal_cloaked_fleets = models.BooleanField(default=False)

    class Meta:
        unique_together = [['player', 'target_player']]

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if update_fields and 'stance' in update_fields and 'pending_stance' not in update_fields:
            self.pending_stance = self.stance
            kwargs['update_fields'] = list(set(update_fields) | {'pending_stance'})
        # Preserve historical behavior for callers that only set `stance` on create.
        elif self._state.adding and self.pending_stance == 'NEUTRAL' and self.stance != 'NEUTRAL':
            self.pending_stance = self.stance
        if self.player_id and self.target_player_id:
            if self.player_id == self.target_player_id:
                raise ValidationError('Players cannot set diplomacy toward themselves.')
            if self.player.game_id != self.target_player.game_id:
                raise ValidationError('Diplomacy targets must be in the same game.')
        super(PlayerDiplomaticStance, self).save(*args, **kwargs)


class FleetOrders(AbstractGameObject):
    """Movement and action orders for a fleet."""
    ORDER_TYPE_CHOICES = [
        ('MOVE', 'Move'),
        ('INTERCEPT', 'Intercept'),
        ('REFUEL', 'Refuel'),
        ('TRANSFER', 'Transfer'),
        ('GIVE', 'Transfer Fleet'),
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
    original_warpfactor = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(14)],
    )
    overmax_risk_checked = models.BooleanField(default=False)
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
            on_delete=models.SET_NULL)

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
    transfer_fuel = models.FloatField(default=0.0)
    transfer_player = models.ForeignKey(
        Player,
        null=True,
        blank=True,
        related_name='+',
        on_delete=models.SET_NULL,
    )

    # Patrol parameters
    patrol_radius = models.IntegerField(default=0)
    intercept_speed = models.IntegerField(default=5)
    patrol_generated = models.BooleanField(default=False)
    last_contact_year = models.IntegerField(null=True, blank=True)

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
        elif self.order_type == 'GIVE':
            if self.transfer_player_id:
                return self.transfer_player.name
            return "Abandoned"
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

    def save(self, *args, **kwargs):
        if self.original_warpfactor is None:
            self.original_warpfactor = self.warpfactor
        super(FleetOrders, self).save(*args, **kwargs)

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

    class Meta:
        unique_together = [['game', 'short_id']]


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
        ('SPECIAL', 'Special'),
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
        unique_together = [['category', 'level', 'name'], ['short_id']]

    def __str__(self):
        return '%s L%s: %s' % (self.category.name, self.level, self.name)


class DiplomaticContract(AbstractGameObject):
    TEMPERATURE_PROPOSE = 'PROPOSE'
    TEMPERATURE_REQUEST = 'REQUEST'
    TEMPERATURE_DEMAND = 'DEMAND'
    TEMPERATURE_CHOICES = [
        (TEMPERATURE_PROPOSE, 'Propose'),
        (TEMPERATURE_REQUEST, 'Request'),
        (TEMPERATURE_DEMAND, 'Demand'),
    ]

    STATUS_DRAFT = 'DRAFT'
    STATUS_SENT = 'SENT'
    STATUS_ACCEPTED = 'ACCEPTED'
    STATUS_FULFILLED = 'FULFILLED'
    STATUS_DECLINED = 'DECLINED'
    STATUS_COUNTERED = 'COUNTERED'
    STATUS_EXPIRED = 'EXPIRED'
    STATUS_REVOKED = 'REVOKED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SENT, 'Sent'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_FULFILLED, 'Fulfilled'),
        (STATUS_DECLINED, 'Declined'),
        (STATUS_COUNTERED, 'Countered'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_REVOKED, 'Revoked'),
    ]

    CONDITION_EXCHANGE = 'EXCHANGE'
    CONDITION_OR_ELSE = 'OR_ELSE'
    CONDITION_CHOICES = [
        (CONDITION_EXCHANGE, 'In Exchange For'),
        (CONDITION_OR_ELSE, 'Or Else'),
    ]

    CLAUSE_NOTHING = 'NOTHING'
    CLAUSE_TECHNOLOGY = 'TECHNOLOGY'
    CLAUSE_STANCE = 'STANCE'
    CLAUSE_RESOURCE_TO_WORLD = 'RESOURCE_TO_WORLD'
    CLAUSE_RESOURCE_ON_GIVEN_FLEET = 'RESOURCE_ON_GIVEN_FLEET'
    CLAUSE_FLEET_BY_SHIP_COUNT = 'FLEET_BY_SHIP_COUNT'
    CLAUSE_SPECIFIC_FLEET = 'SPECIFIC_FLEET'
    CLAUSE_SPECIFIC_COLONY = 'SPECIFIC_COLONY'
    CLAUSE_REPORT = 'REPORT'
    CLAUSE_VAGUE_THREAT = 'VAGUE_THREAT'
    CLAUSE_CHOICES = [
        (CLAUSE_NOTHING, 'Nothing'),
        (CLAUSE_TECHNOLOGY, 'Technology'),
        (CLAUSE_STANCE, 'Stance'),
        (CLAUSE_RESOURCE_TO_WORLD, 'Resources To World'),
        (CLAUSE_RESOURCE_ON_GIVEN_FLEET, 'Resources On Given Fleet'),
        (CLAUSE_FLEET_BY_SHIP_COUNT, 'Fleet By Ship Count'),
        (CLAUSE_SPECIFIC_FLEET, 'Specific Fleet'),
        (CLAUSE_SPECIFIC_COLONY, 'Specific Colony'),
        (CLAUSE_REPORT, 'Report'),
        (CLAUSE_VAGUE_THREAT, 'Vague Threat'),
    ]

    sender = models.ForeignKey(
        Player,
        related_name='sent_diplomatic_contracts',
        on_delete=models.CASCADE,
    )
    recipient = models.ForeignKey(
        Player,
        related_name='received_diplomatic_contracts',
        on_delete=models.CASCADE,
    )
    countered_from = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        related_name='counter_offers',
        on_delete=models.SET_NULL,
    )
    temperature = models.CharField(
        max_length=8,
        choices=TEMPERATURE_CHOICES,
        default=TEMPERATURE_PROPOSE,
    )
    offer_condition_type = models.CharField(
        max_length=16,
        choices=CONDITION_CHOICES,
        default=CONDITION_EXCHANGE,
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    sent_year = models.IntegerField(default=0)
    accepted_year = models.IntegerField(null=True, blank=True)
    handled_year = models.IntegerField(null=True, blank=True)
    fulfilled_year = models.IntegerField(null=True, blank=True)
    expires_year = models.IntegerField(default=0)
    extend_on_accept_years = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    request_clause_type = models.CharField(
        max_length=24,
        choices=CLAUSE_CHOICES,
        default=CLAUSE_NOTHING,
    )
    request_technology = models.ForeignKey(
        'Technology',
        null=True,
        blank=True,
        related_name='+',
        on_delete=models.SET_NULL,
    )
    request_stance = models.CharField(
        max_length=8,
        choices=Player.STANCE_CHOICES,
        blank=True,
        default='',
    )
    request_ship_count = models.IntegerField(default=0)
    request_ironium = models.IntegerField(default=0)
    request_boranium = models.IntegerField(default=0)
    request_germanium = models.IntegerField(default=0)
    request_resource_x = models.IntegerField(default=0)
    request_resource_y = models.IntegerField(default=0)
    request_resource_z = models.IntegerField(default=0)
    request_colonists = models.IntegerField(default=0)
    request_suggested_star = models.ForeignKey(
        Star,
        null=True,
        blank=True,
        related_name='+',
        on_delete=models.SET_NULL,
    )
    request_star = models.ForeignKey(
        Star,
        null=True,
        blank=True,
        related_name='+',
        on_delete=models.SET_NULL,
    )
    request_report_target_type = models.CharField(max_length=10, blank=True, default='')
    request_report_target_id = models.UUIDField(null=True, blank=True)

    offer_clause_type = models.CharField(
        max_length=24,
        choices=CLAUSE_CHOICES,
        default=CLAUSE_NOTHING,
    )
    offer_technology = models.ForeignKey(
        'Technology',
        null=True,
        blank=True,
        related_name='+',
        on_delete=models.SET_NULL,
    )
    offer_stance = models.CharField(
        max_length=8,
        choices=Player.STANCE_CHOICES,
        blank=True,
        default='',
    )
    offer_fleet = models.ForeignKey(
        Fleet,
        null=True,
        blank=True,
        related_name='+',
        on_delete=models.SET_NULL,
    )
    offer_fleet_include_report = models.BooleanField(default=True)
    offer_star = models.ForeignKey(
        Star,
        null=True,
        blank=True,
        related_name='+',
        on_delete=models.SET_NULL,
    )
    offer_report_target_type = models.CharField(max_length=10, blank=True, default='')
    offer_report_target_id = models.UUIDField(null=True, blank=True)

    progress_ironium = models.IntegerField(default=0)
    progress_boranium = models.IntegerField(default=0)
    progress_germanium = models.IntegerField(default=0)
    progress_resource_x = models.IntegerField(default=0)
    progress_resource_y = models.IntegerField(default=0)
    progress_resource_z = models.IntegerField(default=0)
    progress_colonists = models.IntegerField(default=0)
    progress_ship_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
        unique_together = [['game', 'short_id']]

    def clean(self):
        super(DiplomaticContract, self).clean()
        if self.sender_id and self.recipient_id:
            if self.sender_id == self.recipient_id:
                raise ValidationError('Diplomatic requests cannot target the same player.')
            if self.sender.game_id != self.recipient.game_id or self.sender.game_id != self.game_id:
                raise ValidationError('Diplomatic requests must remain within one game.')
        if self.request_suggested_star_id and self.request_suggested_star.game_id != self.game_id:
            raise ValidationError('Suggested destination star must belong to this game.')
        if (
            self.request_suggested_star_id and self.sender_id and
            self.request_suggested_star.player_id != self.sender_id
        ):
            raise ValidationError('Suggested destination star must belong to the sending player.')
        if self.request_star_id and self.request_star.game_id != self.game_id:
            raise ValidationError('Requested colony must belong to this game.')
        if (
            self.request_star_id and self.recipient_id and
            self.request_star.player_id != self.recipient_id
        ):
            raise ValidationError('Requested colony must belong to the receiving player.')
        if self.offer_fleet_id and self.offer_fleet.game_id != self.game_id:
            raise ValidationError('Offered fleet must belong to this game.')
        if (
            self.offer_fleet_id and self.sender_id and
            self.offer_fleet.player_id != self.sender_id
        ):
            raise ValidationError('Offered fleet must belong to the sending player.')
        if self.offer_star_id and self.offer_star.game_id != self.game_id:
            raise ValidationError('Offered colony must belong to this game.')
        if (
            self.offer_star_id and self.sender_id and
            self.offer_star.player_id != self.sender_id
        ):
            raise ValidationError('Offered colony must belong to the sending player.')

    @property
    def is_handled(self):
        return self.status in (
            self.STATUS_ACCEPTED,
            self.STATUS_FULFILLED,
            self.STATUS_DECLINED,
            self.STATUS_COUNTERED,
            self.STATUS_EXPIRED,
            self.STATUS_REVOKED,
        )

    @property
    def is_unanswered(self):
        return self.status == self.STATUS_SENT

    def __str__(self):
        return '%s -> %s (%s)' % (
            getattr(self.sender, 'name', 'Unknown'),
            getattr(self.recipient, 'name', 'Unknown'),
            self.status,
        )


class PlayerTechnologyGrant(models.Model):
    player = models.ForeignKey(
        Player,
        related_name='technology_grants',
        on_delete=models.CASCADE,
    )
    technology = models.ForeignKey(
        Technology,
        related_name='player_grants',
        on_delete=models.CASCADE,
    )
    source_contract = models.ForeignKey(
        DiplomaticContract,
        null=True,
        blank=True,
        related_name='technology_grants',
        on_delete=models.SET_NULL,
    )
    granted_by_player = models.ForeignKey(
        Player,
        null=True,
        blank=True,
        related_name='technology_grants_given',
        on_delete=models.SET_NULL,
    )
    granted_year = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['player', 'technology']]
        ordering = ['technology__category', 'technology__level', 'technology__name']

    def clean(self):
        super(PlayerTechnologyGrant, self).clean()
        if self.source_contract_id and self.player_id:
            if self.source_contract.game_id != self.player.game_id:
                raise ValidationError('Technology grants must stay within the same game.')

    def __str__(self):
        return '%s granted %s' % (
            getattr(self.player, 'name', 'Unknown'),
            getattr(self.technology, 'name', 'Unknown technology'),
        )


class HullDesign(models.Model):
    """Staff-authored hull blueprint prototype (no gameplay integration yet)."""
    technology = models.OneToOneField(
        'Technology',
        null=True,
        blank=True,
        related_name='hull_design',
        on_delete=models.CASCADE,
        limit_choices_to={'tech_type': 'HULL'},
    )
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
        ('SCANNER', 'Scanner'),
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

    class Meta:
        unique_together = [['game', 'short_id']]


class GameInvitation(UUIDMixin):
    """Invitation to join a game, by account or email."""
    game = models.ForeignKey(Game, related_name='invitations', on_delete=models.CASCADE)
    account = models.ForeignKey(Account, null=True, blank=True,
                                related_name='game_invitations', on_delete=models.CASCADE)
    email = models.EmailField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['game', 'account'], ['game', 'email'], ['short_id']]

    def __str__(self):
        target = self.account.alias if self.account else self.email
        return f'{self.game.name}: {target}'


class Spectator(models.Model):
    """Spectator record for a game (consent to never join)."""
    game = models.ForeignKey(Game, related_name='spectators', on_delete=models.CASCADE)
    account = models.ForeignKey(Account, related_name='spectatorships', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    consented_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['game', 'account']]
        ordering = ['-consented_at']

    def __str__(self):
        return f'{self.game.name}: {self.account.alias}'


PRODUCTION_COSTS = {
    'BUILD_MINE': {'bp': 0, 'ironium': 10, 'boranium': 0, 'germanium': 0, 'colonists': 1000},
    'BUILD_FACTORY': {'bp': 0, 'ironium': 20, 'boranium': 0, 'germanium': 0, 'colonists': 1000},
    'BUILD_LAB': {'bp': 20, 'ironium': 50, 'boranium': 20, 'germanium': 20, 'colonists': 0},
    'BUILD_DEFENSE': {'bp': 50, 'ironium': 100, 'boranium': 50, 'germanium': 50, 'colonists': 0},
    'BUILD_SHIPYARD': {'bp': 100, 'ironium': 250, 'boranium': 50, 'germanium': 100,
                       'colonists': 0},
    'BUILD_ADMINISTRATION': {'bp': 120, 'ironium': 300, 'boranium': 0,
                             'germanium': 450, 'colonists': 0},
    'REMOVE_ADMINISTRATION': {'bp': 40, 'ironium': 0, 'boranium': 0,
                              'germanium': 0, 'colonists': 0},
    'BUILD_FLEET': {'bp': 50, 'ironium': 100, 'boranium': 200, 'germanium': 200, 'colonists': 0},
    'TERRAFORM_GRAVITY': {'bp': 50, 'ironium': 375, 'boranium': 75, 'germanium': 50, 'colonists': 0},
    'TERRAFORM_TEMPERATURE': {'bp': 50, 'ironium': 100, 'boranium': 330, 'germanium': 70, 'colonists': 0},
    'TERRAFORM_RADIATION': {'bp': 50, 'ironium': 25, 'boranium': 240, 'germanium': 240, 'colonists': 0},
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
        ('BUILD_ADMINISTRATION', 'Build Administration'),
        ('REMOVE_ADMINISTRATION', 'Remove Administration'),
    ]

    star = models.ForeignKey(Star, related_name='production_orders',
            on_delete=models.CASCADE)
    order_type = models.CharField(max_length=24, choices=ORDER_TYPES)
    position = models.IntegerField(default=0)
    repeat = models.BooleanField(default=False)
    added_by_micromanager = models.BooleanField(default=False)
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
        unique_together = [['game', 'short_id']]


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
        unique_together = [['player', 'target_type', 'target_id'], ['game', 'short_id']]

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
