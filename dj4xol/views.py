from django.http import HttpResponse
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.shortcuts import render
from django.urls import resolve
from itertools import chain

from .models import Game, Ship, Star
from .decorators import player_only_view, registration_required
from .data import GameTurn


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
    open_games = Game.objects.filter(joinable=True, ended=False).all()
    return render(request, 'dj4xol/games.html', {'player': player, 'my_games': my_games})


@player_only_view()
def starmap(request, game_id):
    """
    A rudimentary map viewer.
    """
    game = Game.objects.get(pk=game_id)
    url = request.path

    x = request.GET.get('x', None)
    y = request.GET.get('y', None)
    selected = request.GET.get('sel', None)
    if selected:
        if selected.startswith('star') or selected.startswith('ship'):
            sel_id = int(selected[4:])
            sel_class = selected[:4]
            if sel_class == 'star':
                selected = game.stars.get(pk=sel_id)
            elif sel_class == 'ship':
                selected = game.ships.get(pk=sel_id)
            x = selected.x
            y = selected.y

    if x and y:
        x = int(x)
        y = int(y)
        stars = game.stars.filter(x=x, y=y).all()
        ships = game.ships.filter(x=x, y=y).all()
        at_cursor = list(chain(stars, ships))
        if not selected:
            try:
                selected = at_cursor[0]
            except IndexError:
                selected = None

    detail = ''
    if selected:
        detail = "<div id='detail'><h2>%s</h2> at %i,%i " % (selected.name, x, y)
        if selected.player:
            detail += "owner: " + selected.player.django_user.username
        for item in at_cursor:
            if isinstance(item, Star):
                identifier = "%s%i" % ('star', item.pk)
            elif isinstance(item, Ship):
                identifier = "%s%i" % ('ship', item.pk)
            detail += "<li><a href=\"%s?sel=%s\">%s</a></li>" % (url,
                    identifier, item.name)
        detail += "</div>"


    gamemap = [['&nbsp' for _ in range(game.map_size_y + 1)] for _ in
            range(game.map_size_x + 1)]

    for star in game.stars.all():
        if x == star.x and y == star.y:
            color = 'blue'
        elif star.player == request.user.dj4xolplayer:
            color = 'green'
        elif star.player == None:
            color = 'white'
        else:
            color = 'red'

        gamemap[star.x][star.y] = '<a style="color:%s;text-decoration:none;" \
                                  title="%s" href=%s?x=%i&y=%i>+</a>' % (color, 
                                  star.name, url, star.x, star.y)
    for ship in game.ships.all():
        if x == ship.x and y == ship.y:
            color = 'blue'
        elif ship.player == request.user.dj4xolplayer:
            color = 'green'
        elif ship.player == None:
            color = 'white'
        else:
            color = 'red'

        if gamemap[ship.x][ship.y] != '&nbsp':
            identifier = '*'
        else:
            identifier = '^'

        gamemap[ship.x][ship.y] = '<a style="color:%s;text-decoration:none;" \
                                  title="%s" href=%s?x=%i&y=%i>%s</a>' % (color,
                                  ship.name, url, ship.x, ship.y, identifier)

    html = "<html><body>"
    html += '<script src="//ajax.googleapis.com/ajax/libs/jquery/2.0.0/jquery.min.js"></script>'
    html += '<script type="text/javascript" src="' + \
            static('dj4xol/mapscrollpersist.js') + '"></script>'
    html += "<h1>%s</h1>" % (game.name)
    html += "<p>%s</p>" % (game.description)
    html += '<div><h2>Starmap</h2><div id="starmap" style="height:600px;width:600px;border:1px solid #ccc;background-color:black;color:white;font-family:monospace;overflow:auto;font-size:10px;">'
    html += '<div id="maparea">'
    for x in gamemap:
        for y in x:
            html += y
        html += "<br />"
    html += "</div></div></div>"
    html += detail
    html += "</body></html>"
    return HttpResponse(html)
