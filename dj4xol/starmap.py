from .models import Game, Player, Ship, Star

class starMap():
    def __init__(self, game, player):
        self.game = game
        self.player = player
        self.stars = game.stars.all()
        self.ships = game.ships.all()
        self.map = self.render_map()

    def render_map(self):
        """Render a map of the stars in the game using HTML canvas. """
        for star in self.stars:
            