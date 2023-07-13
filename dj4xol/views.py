from django.http import HttpResponse
from django.shortcuts import render
from django.urls import resolve

from dj4xol.objectdetails import DetailBuilder

from .models import Game, ServerSettings
from .decorators import registration_required, player_only_view
from .turn import GameTurn
from .starmap import StarMap


@registration_required()
def gamelist(request):
    """
    index of all games the user can see
    """
    player = request.user.dj4xolplayer
    my_games_count = player.games.filter(ended=False).count()
    my_games = player.games.filter(ended=False).all()
    hosted_games_count = Game.objects.filter(owner=player).count()
    hosted_games = Game.objects.filter(owner=player).all()
    open_games = Game.objects.filter(public=True, ended=False).all()
    return render(request, 'dj4xol/games.html', 
                  {'player': player,
                   'my_games': my_games,
                   'open_games': open_games,
                   'server_settings': ServerSettings.all_to_dict()})

def join_game(request, game_id):
    """
    join a game
    """
    game = Game.objects.get(pk=game_id)
    player = request.user.dj4xolplayer
    game.players.add(player)
    game.save()
    return HttpResponse('joined %s' % game.name)

@player_only_view()
def starmap(request, game_id):
    """
    A rudimentary map viewer.
    """
    game = Game.objects.get(pk=game_id)
    player = request.user.dj4xolplayer
    starmap = StarMap(game, player).render_map()
    
    url = request.path
    x = request.GET.get('x', None)
    y = request.GET.get('y', None)

    selected = request.GET.get('sel', None)
    detail = DetailBuilder(game, x, y, selected).build_detail()

    return render(request, 'dj4xol/main.html', 
                  {'game': game,
                   'player': player,
                   'starmap': starmap,
                   'detail': detail})

