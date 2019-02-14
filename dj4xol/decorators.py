from django.http import HttpResponseForbidden, HttpResponseNotFound
from django.contrib.auth.decorators import login_required

from .models import Game, Player


def registration_required():
    """
    Decorator that checks whether the user has a player account
    """
    def decorate(func):
        @login_required()
        def wrapper(request, *args, **kwargs):
            if Player.objects.filter(django_user=request.user).exists():
                return func(request, *args, **kwargs)
            else:
                return HttpResponseForbidden('<h1>You must register to view this page</h1>')

        return wrapper
    return decorate


def player_only_view():
    """
    Decorator that checks whether a user is a member of the game
    """
    def decorate(func):
        @login_required()
        def wrapper(request, game_id, *args, **kwargs):
            if request.user.dj4xolplayer in Game.objects.get(pk=game_id).players.all():
                return func(request, game_id, *args, **kwargs)
            else:
                return HttpResponseForbidden('<h1>You are not a member of this game</h1>')

        return wrapper
    return decorate


def owner_only_view():
    """
    Decorator that checks whether a user is the owner of a game
    """
    def decorate(func):
        @login_required()
        def wrapper(request, game_id, *args, **kwargs):
            if request.user.dj4xolplayer == Game.objects.get(pk=game_id).owner:
                return func(request, game_id, *args, **kwargs)
            else:
                return HttpResponseForbidden('<h1>You are not the owner of this game</h1>')

        return wrapper
    return decorate
