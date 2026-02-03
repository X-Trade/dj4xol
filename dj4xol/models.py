from django.db import models
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
    return random.randint(0, 100)
def random_environmental_init():
    return random.random() * 2.0
def random_capacity_init():
    """Random base capacity between 5bn and 15bn (stored in millions)."""
    return random.randint(5000, 15000)


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
        """Get a setting by key, creating from fixtures if not found."""
        try:
            return cls.objects.get(pk=key).value
        except cls.DoesNotExist:
            defaults = cls._load_defaults()
            if key in defaults:
                fields = defaults[key]
                setting = cls.objects.create(
                    key=key,
                    value=fields.get('value', ''),
                    description=fields.get('description', '')
                )
                return setting.value
            return default


class Account(models.Model):
    """A dj4xol account linked to a Django user."""
    django_user = models.OneToOneField(auth_models.User, primary_key=True,
            related_name="dj4xol_account", on_delete=models.PROTECT)
    full_name = models.CharField(max_length=60)
    alias = models.CharField(max_length=30, unique=True)
    email = models.EmailField()

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
        return list(chain(self.stars.filter(x=x, y=y).all(), self.fleets.filter(x=x, y=y).all()))

    def get_star_namer(self):
        if not self._star_namer:
            self._star_namer = StarNamer(self.get_star_names())
        return self._star_namer


class AbstractGameObject(UUIDMixin):
    game = models.ForeignKey(Game, related_name="%(class)ss",
            on_delete=models.CASCADE)

    def __str__(self):
        return self.short_id

    def save(self, *args, **kwargs):
        if not self.short_id:
            # Combine game prefix (4 chars) + object suffix (8 chars) = 12 chars
            self.short_id = self.game.short_id[:4] + self.id.hex[-8:]
        super(UUIDMixin, self).save(*args, **kwargs)

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


class Fleet(AbstractMapObject):
    """A group of ships traveling together."""
    name = models.CharField(max_length=30)
    player = models.ForeignKey('Player', related_name='fleets',
            on_delete=models.CASCADE)
    # Heading in degrees: 0 = north, 90 = east, 180 = south, 270 = west
    heading = models.FloatField(default=0.0)


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

    ironium = models.IntegerField(default=random_resource_init,
                                  validators=[MinValueValidator(0), MaxValueValidator(100)])
    boranium = models.IntegerField(default=random_resource_init,
                                  validators=[MinValueValidator(0), MaxValueValidator(100)])
    germanium = models.IntegerField(default=random_resource_init,
                                  validators=[MinValueValidator(0), MaxValueValidator(100)])

    colonists = models.IntegerField(default=0)
    # Base carrying capacity (in millions), effective capacity = base * habitability
    base_capacity = models.IntegerField(default=random_capacity_init)

    # Economic infrastructure
    mines = models.IntegerField(default=0)
    factories = models.IntegerField(default=0)


class ServerRace(UUIDMixin, HabitabilityMixin):
    name = models.CharField(max_length=16)
    plural_name = models.CharField(max_length=16)
    formal_name = models.CharField(max_length=32)
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
    formal_name = models.CharField(max_length=32, null=True, default=None)
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
        if self.formal_name is None:
            self.formal_name = self.name
        super(Player, self).save(*args, **kwargs)


class FleetOrders(AbstractGameObject):
    """Movement and action orders for a fleet."""
    fleet = models.ForeignKey(Fleet, related_name="orders",
            on_delete=models.CASCADE)
    repeat = models.BooleanField(default=False)
    warpfactor = models.IntegerField(default=0,
                                     validators=[MinValueValidator(0), MaxValueValidator(13)])
    x = models.IntegerField(null=True)
    y = models.IntegerField(null=True)
    target_star = models.ForeignKey(Star, null=True, related_name='+',
            on_delete=models.CASCADE)
    target_fleet = models.ForeignKey(Fleet, null=True, related_name='+',
            on_delete=models.CASCADE)


class GameMessage(AbstractGameObject):
    CATEGORY_CHOICES = [
        ('GENERAL', 'General'),
        ('DIPLOMATIC', 'Diplomatic'),
        ('ENVIRONMENTAL', 'Environmental'),
        ('POPULATION', 'Population'),
        ('RANDOM', 'Random Event'),
        ('COMBAT', 'Combat'),
        ('PRODUCTION', 'Production'),
    ]

    player = models.ForeignKey(Player, related_name='messages',
            on_delete=models.CASCADE)
    message = models.TextField()
    year = models.IntegerField()
    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES, default='GENERAL')

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


class ProductionOrder(AbstractGameObject):
    """Production order for a star/planet."""
    ORDER_TYPES = [
        ('TERRAFORM_GRAVITY', 'Terraform Gravity (1%)'),
        ('TERRAFORM_TEMPERATURE', 'Terraform Temperature (1%)'),
        ('TERRAFORM_RADIATION', 'Terraform Radiation (1%)'),
        ('BUILD_FLEET', 'Build Fleet'),
        ('BUILD_MINE', 'Build Mine'),
        ('BUILD_FACTORY', 'Build Factory'),
    ]

    star = models.ForeignKey(Star, related_name='production_orders',
            on_delete=models.CASCADE)
    order_type = models.CharField(max_length=24, choices=ORDER_TYPES)
    position = models.IntegerField(default=0)

    class Meta:
        ordering = ['position']
