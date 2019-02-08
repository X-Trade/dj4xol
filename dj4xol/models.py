from django.db import models
from django.contrib.auth import models as auth_models
from django.core.validators import MaxValueValidator, MinValueValidator


class Player(models.Model):
    django_user = models.OneToOneField(auth_models.User, primary_key=True,
            related_name="dj4xolplayer", on_delete = models.PROTECT)
    full_name = models.CharField(max_length=60)
    alias = models.CharField(max_length=30, unique=True)
    email = models.EmailField()


class Game(models.Model):
    name = models.CharField(max_length=30)
    players = models.ManyToManyField(Player, related_name="games")
    owner = models.ForeignKey(Player, related_name="mygames",
            on_delete=models.CASCADE)
    description = models.TextField()
    map_size_x = models.IntegerField()
    map_size_y = models.IntegerField()


class AbstractGameObject(models.Model):
    game = models.ForeignKey(Game, related_name="%(class)ss",
            on_delete=models.CASCADE)

    class Meta:
        abstract = True


class AbstractMapObject(AbstractGameObject):
    x = models.IntegerField()
    y = models.IntegerField()

    class Meta:
        abstract = True


class Ship(AbstractMapObject):
    name = models.CharField(max_length=30)
    player = models.ForeignKey(Player, related_name = 'ships',
            on_delete=models.CASCADE)


class Star(AbstractMapObject):
    name = models.CharField(max_length=30)
    player = models.ForeignKey(Player, null=True, default=None, related_name =
            'stars', on_delete=models.CASCADE)


class ShipOrders(AbstractGameObject):
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

