from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator


class Player(models.Model):
    firstname = models.CharField(max_length=30)
    lastname = models.CharField(max_length=30)
    alias = models.CharField(max_length=30)
    email = models.EmailField()


class Game(models.Model):
    name = models.CharField(max_length=30)
    players = models.ManyToManyField(Player, related_name="games")
    description = models.TextField()
    map_size_x = models.IntegerField()
    map_size_y = models.IntegerField()


class AbstractGameObject(models.Model):
    game = models.ForeignKey(Game, related_name="%(class)ss")

    class Meta:
        abstract = True


class AbstractMapObject(AbstractGameObject):
    x = models.IntegerField()
    y = models.IntegerField()

    class Meta:
        abstract = True


class Ship(AbstractMapObject):
    player = models.ForeignKey(Player, related_name = 'ships')


class Star(AbstractMapObject):
    name = models.CharField(max_length=30)
    player = models.ForeignKey(Player, null=True, default=None, related_name = 
                               'stars')


class ShipOrders(AbstractGameObject):
    ship = models.ForeignKey(Ship, related_name="orders")
    repeat = models.BooleanField(default = False)
    warpfactor = models.IntegerField(default = 0, 
                                     validators=[MinValueValidator(0), MaxValueValidator(13)])
    x = models.IntegerField(null=True)
    y = models.IntegerField(null=True)
    target_star = models.ForeignKey(Star, null=True, related_name='+')
    target_ship = models.ForeignKey(Ship, null=True, related_name='+')

