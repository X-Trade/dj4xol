from django.http import HttpResponse
from django.urls import resolve
from itertools import chain

from .models import Game, Ship, Star
from .decorators import player_only_view
from .data import GameTurn


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

    detail = ''
    if x and y:
        x = int(x)
        y = int(y)
        stars = game.stars.filter(x=x, y=y).all()
        ships = game.ships.filter(x=x, y=y).all()
        at_cursor = chain(stars, ships)
        if not selected:
            selected = stars[0]
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


    gamemap = [['&nbsp' for _ in range(game.map_size_y + 1)] for _ in
            range(game.map_size_x + 1)]

    for star in game.stars.all():
        if x == star.x and y == star.y:
            color = 'blue'
        elif star.player == request.user.dj4xolplayer:
            color = 'green'
        else:
            color = 'white'
        gamemap[star.x][star.y] = '<a style="color:%s;text-decoration:none;" \
                                  href=%s?x=%i&y=%i>+</a>' % (color, url, star.x, star.y)
    for ship in game.ships.all():
        if gamemap[ship.x][ship.y] == '+':
            gamemap[ship.x][ship.y] = '*'
        else:
            gamemap[ship.x][ship.y] = '^'

    html = "<html><body>"
    html += "<h1>%s</h1>" % (game.name)
    html += "<p>%s</p>" % (game.description)
    html += '<div id=\'map\'><h2>Starmap</h2><div style="height:600px;width:600px;border:1px solid #ccc;background-color:black;color:white;font-family:monospace;overflow:auto;font-size:10px;">'
    for x in gamemap:
        for y in x:
            html += y
        html += "<br />"
    html += "</div></div>"
    html += detail
    html += "</body></html>"
    return HttpResponse(html)
