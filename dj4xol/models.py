from django.db import models
from django import forms
from django.contrib.auth import models as auth_models
from django.core.validators import MaxValueValidator, MinValueValidator
from itertools import chain
from .starnamer import StarNamer
import random

def random_resource_init():
    return random.randint(0, 100)
def random_environmental_init():
    return random.random() * 2.0


class ServerSettings(models.Model):
    key = models.CharField(max_length=30, primary_key=True, unique=True)
    value = models.CharField(max_length=30)
    description = models.CharField(max_length=60)
    modified = models.DateTimeField(auto_now=True, null=True)
    modified_by = models.ForeignKey(auth_models.User, on_delete=models.PROTECT, null=True)

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
    
class Player(models.Model):
    django_user = models.OneToOneField(auth_models.User, primary_key=True,
            related_name="dj4xolplayer", on_delete = models.PROTECT)
    full_name = models.CharField(max_length=60)
    alias = models.CharField(max_length=30, unique=True)
    email = models.EmailField()

    def __str__(self):
        return '%i:%s' % (self.pk, self.alias)

class Game(models.Model):
    name = models.CharField(max_length=30)
    players = models.ManyToManyField(Player, related_name="games")
    owner = models.ForeignKey(Player, related_name="mygames",
            on_delete=models.CASCADE)
    description = models.TextField()
    map_size_x = models.IntegerField()
    map_size_y = models.IntegerField()
    joinable = models.BooleanField(default = False) # anybody who can see can join
    public = models.BooleanField(default = False) # anybody can view
    ended = models.BooleanField(default = False)
    year = models.IntegerField(default=2100)

    _star_names = []
    _star_namer = None

    def __str__(self):
        return '%i %s' % (self.id, self.name)
    
    def get_star_names(self):
        return [star["name"] for star in self.stars.values("name").all()]

    def get_object_at(self, x, y):
        return self.stars.filter(x=x, y=y).first() or self.ships.filter(x=x, y=y).first() or None
    
    def get_all_objects_at(self, x, y):
        return list(chain(self.stars.filter(x=x, y=y).all(), self.ships.filter(x=x, y=y).all()))
    
    def get_star_namer(self):
        if not self._star_namer:
            self._star_namer = StarNamer(self.get_star_names())
        return self._star_namer


class AbstractGameObject(models.Model):
    game = models.ForeignKey(Game, related_name="%(class)ss",
            on_delete=models.CASCADE)

    def __str__(self):
        return 'Game%i:%s%i' % (self.game.id, self.__class__.__name__, self.id)

    class Meta:
        abstract = True


class AbstractMapObject(AbstractGameObject):
    x = models.IntegerField()
    y = models.IntegerField()

    class Meta:
        abstract = True

class ServerRaceType(models.Model):
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


class ServerRace(AbstractGameObject):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=16)
    plural_name = models.CharField(max_length=16)
    formal_name = models.CharField(max_length=32)
    public = models.BooleanField(default=False)
    owner = models.ForeignKey(Player, related_name="public_races",
                                      null=True, default=None,
                                      on_delete=models.SET_NULL)
    description = models.TextField(null=True, default=None)
    race_type = models.ForeignKey(ServerRaceType)

class PlayerRace(AbstractGameObject):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=16)
    plural_name = models.CharField(max_length=16, null=True, default=None)
    formal_name = models.CharField(max_length=32, null=True, default=None)
    player = models.ForeignKey(Player, related_name="races",
                                      null=True, default=None,
                                      on_delete=models.SET_NULL)
    description = models.TextField(null=True, default=None)
    race_type = models.ForeignKey(ServerRaceType)

    def save(self, *args, **kwargs):
        if self.plural_name is None:
            self.plural_name = self.name + 's'
        if self.formal_name is None:
            self.formal_name = self.name
        super(PlayerRace, self).save(*args, **kwargs)


class Ship(AbstractMapObject):
    #TODO: Rename to Fleet?
    name = models.CharField(max_length=30)
    player = models.ForeignKey(Player, related_name = 'ships',
            on_delete=models.CASCADE)

class Star(AbstractMapObject):
    name = models.CharField(max_length=30)
    player = models.ForeignKey(Player, null=True, default=None, related_name =
            'stars', on_delete=models.CASCADE)
    gravity = models.FloatField(default=random_environmental_init,
                                validators=[MinValueValidator(0.0), MaxValueValidator(2.0)])
    temperature = models.FloatField(default=random_environmental_init,
                                validators=[MinValueValidator(0.0), MaxValueValidator(2.0)])
    radiation = models.FloatField(default=random_environmental_init,
                                validators=[MinValueValidator(0.0), MaxValueValidator(2.0)])
    gravity_adjustment = models.FloatField(default=0.0,
                                validators=[MinValueValidator(-1.0), MaxValueValidator(1.0)])
    temperature_adjustment = models.FloatField(default=0.0,
                                validators=[MinValueValidator(-1.0), MaxValueValidator(1.0)])
    radiation_adjustment = models.FloatField(default=0.0,
                                validators=[MinValueValidator(-1.0), MaxValueValidator(1.0)])

    ironium = models.IntegerField(default=random_resource_init,
                                  validators=[MinValueValidator(0), MaxValueValidator(100)])
    boranium = models.IntegerField(default=random_resource_init,
                                  validators=[MinValueValidator(0), MaxValueValidator(100)])
    germanium = models.IntegerField(default=random_resource_init,
                                  validators=[MinValueValidator(0), MaxValueValidator(100)])

    colonists = models.IntegerField(default=0)


class ShipOrders(AbstractGameObject):
    #TODO: Rename to FleetOrders?
    ship = models.ForeignKey(Ship, related_name="orders",
            on_delete=models.CASCADE)
    repeat = models.BooleanField(default = False)
    warpfactor = models.IntegerField(default = 0, 
                                     validators=[MinValueValidator(0), MaxValueValidator(13)])
    x = models.IntegerField(null=True)
    y = models.IntegerField(null=True)
    target_star = models.ForeignKey(Star, null=True, related_name='+',
            on_delete=models.CASCADE)
    target_ship = models.ForeignKey(Ship, null=True, related_name='+',
            on_delete=models.CASCADE)

class GameMessage(AbstractGameObject):
    player = models.ForeignKey(Player, related_name='messages',
            on_delete=models.CASCADE)
    message = models.TextField()
    year = models.IntegerField()

    def save(self, *args, **kwargs):
        if self.year is None:
            self.year = self.game.year
        super(GameMessage, self).save(*args, **kwargs)