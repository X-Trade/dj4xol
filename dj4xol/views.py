from django.http import HttpResponse

from .models import Game
from .decorators import player_only_view
from .data import GameTurn


@player_only_view()
def starmap(request, game_id):
    """
    A rudimentary map viewer.
    """
    game = Game.objects.get(pk=game_id)

    gamemap = [['&nbsp' for _ in range(game.map_size_y + 1)] for _ in
            range(game.map_size_x + 1)]

    for star in game.stars.all():
        gamemap[star.x][star.y] = '+'
    for ship in game.ships.all():
        if gamemap[ship.x][ship.y] == '+':
            gamemap[ship.x][ship.y] = '*'
        else:
            gamemap[ship.x][ship.y] = '^'

    html = "<html><body>"
    html += "<h1>%s</h1>" % (game.name)
    html += "<p>%s</p>" % (game.description)
    html += '<h2>Starmap</h2><div style="height:600px;width:600px;border:1px solid #ccc;background-color:black;color:white;font-family:monospace;overflow:auto;">'
    for x in gamemap:
        for y in x:
            html += y
        html += "<br />"
    html += "</div>"
    html += "</body></html>"
    return HttpResponse(html)
