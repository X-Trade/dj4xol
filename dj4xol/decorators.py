from django.http import HttpResponseForbidden, HttpResponseNotFound
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from .models import Game, Account, Player


def registration_required():
    """
    Decorator that checks whether the user has an Account.
    Redirects to registration page if not registered.
    """
    def decorate(func):
        @login_required()
        def wrapper(request, *args, **kwargs):
            if Account.objects.filter(django_user=request.user).exists():
                return func(request, *args, **kwargs)
            else:
                return redirect('dj4xol:register')

        return wrapper
    return decorate


def player_only_view():
    """
    Decorator that checks whether a user is a member of the game.
    Requires user to be logged in and have an Account.
    """
    def decorate(func):
        @login_required()
        def wrapper(request, game_short_id, *args, **kwargs):
            if not hasattr(request.user, 'dj4xol_account'):
                return redirect('dj4xol:register')
            account = request.user.dj4xol_account
            game = Game.objects.get(short_id=game_short_id)
            if Player.objects.filter(game=game, account=account).exists():
                return func(request, game_short_id, *args, **kwargs)
            else:
                return render(request, 'dj4xol/forbidden.html', {
                    'message': 'You are not a member of this game'
                }, status=403)

        return wrapper
    return decorate


def owner_only_view():
    """
    Decorator that checks whether a user is the owner of a game.
    Requires user to be logged in and have an Account.
    """
    def decorate(func):
        @login_required()
        def wrapper(request, game_short_id, *args, **kwargs):
            if not hasattr(request.user, 'dj4xol_account'):
                return redirect('dj4xol:register')
            account = request.user.dj4xol_account
            game = Game.objects.get(short_id=game_short_id)
            if account == game.owner:
                return func(request, game_short_id, *args, **kwargs)
            else:
                return render(request, 'dj4xol/forbidden.html', {
                    'message': 'You are not the owner of this game'
                }, status=403)

        return wrapper
    return decorate
