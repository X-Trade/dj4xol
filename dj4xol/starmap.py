from .models import Game, Player, Ship, Star

class StarMap():
    MAP_SCALE = 5
    HTML_STAR_CLASS = "mapstar"
    HTML_SHIP_CLASS = "mapship"
    CSS = """.mapstar {
                height: 5px;
                width: 5px;
                background-color: #fff;
                box-shadow: inset 0px 0px 3px #bbb;
                border-radius: 50%;
                position: absolute;
             }
             .mapship {
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
        self.ships = game.ships.all()
        self.map = self.render_map()

    def render_map(self, stars=None, ships=None):
        """Render a map of the stars in the game using HTML objects"""
        if stars is None:
            stars = self.stars
        if ships is None:
            ships = self.ships
        
        html=""

        for star in self.stars:
            html+=self.render_star(star)

        for ship in self.ships:
            html+=self.render_ship(ship)
        
        return html
    
    def resolve_html_class(self, object):
        """Resolve the HTML class for an object"""

        if isinstance(object, Star):
            html_class = self.HTML_STAR_CLASS
        elif isinstance(object, Ship):
            html_class = self.HTML_SHIP_CLASS
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
        return f'<a href="{url}"><div class="{html_class}" style="left:{x}px; top:{y}px;"></div></a>'

    def render_star(self, star):
        """Render a star object on map using HTML"""
        return self.render_object(star)
    
    def render_ship(self, ship):
        """Render a ship object on map using HTML"""
        return self.render_object(ship)