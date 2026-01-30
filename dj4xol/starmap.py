from .models import Game, Player, Fleet, Star

class StarMap():
    MAP_SCALE = 5
    HTML_STAR_CLASS = "mapstar"
    HTML_FLEET_CLASS = "mapfleet"
    CSS = """.mapstar {
                height: 5px;
                width: 5px;
                background-color: #fff;
                box-shadow: inset 0px 0px 3px #bbb;
                border-radius: 50%;
                position: absolute;
             }
             .mapfleet {
                height: 5px;
                width: 5px;
                border: solid white;
                border-width: 0 3px 3px 0;
                position: absolute;
                transform: rotate(-45deg);
                -webkit-transform: rotate(-45deg);
             }"""

    def __init__(self, game, player):
        self.game = game
        self.player = player
        self.stars = game.stars.all()
        self.fleets = game.fleets.all()
        self.map = self.render_map()

    def render_map(self, stars=None, fleets=None):
        """Render a map of the stars in the game using HTML objects"""
        if stars is None:
            stars = self.stars
        if fleets is None:
            fleets = self.fleets

        html=""

        for star in self.stars:
            html+=self.render_star(star)

        for fleet in self.fleets:
            html+=self.render_fleet(fleet)

        return html

    def resolve_html_class(self, object):
        """Resolve the HTML class for an object"""

        if isinstance(object, Star):
            html_class = self.HTML_STAR_CLASS
        elif isinstance(object, Fleet):
            html_class = self.HTML_FLEET_CLASS
        else:
            html_class = ""

        if object.player == self.player:
            class_additional = "-owned"
        elif object.player is not None:
            class_additional = "-enemy"
        else:
            class_additional = ""

        return f'{html_class}{class_additional}'

    def render_object(self, object):
        """Render a game object on map using HTML"""
        x=object.x*self.MAP_SCALE
        y=object.y*self.MAP_SCALE
        url="?x=%i&y=%i&sel=%s" % (object.x, object.y, str(object))
        html_class = self.resolve_html_class(object)
        name = object.name
        return f'<a href="{url}" title="{name}"><div class="{html_class}" style="left:{x}px; top:{y}px;"></div></a>'

    def render_star(self, star):
        """Render a star object on map using HTML"""
        return self.render_object(star)

    def render_fleet(self, fleet):
        """Render a fleet object on map using HTML"""
        return self.render_object(fleet)