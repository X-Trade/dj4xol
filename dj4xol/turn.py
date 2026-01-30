from numpy import array as nparray, linalg

class GameTurn():
    """Generate a turn for a game."""
    def __init__(self, game):
        self.game = game

    def generate_turn(self):
        """Generate a turn for the game. Requires at least one player."""
        if not self.game.players.exists():
            raise Exception("cannot generate turn for game with no players")
        self.ship_movements()
        self.clear_empty_planets()
        self.check_join_deadline()
        self.game.year += 1
        self.game.save()

    def generate_turns(self, turns):
        """Generate multiple turns for the game."""
        for _ in range(turns):
            self.generate_turn()

    def ship_movements(self):
        """Move ships according to their orders."""
        for ship in self.game.ships.all():
            self.move_ship(ship).save()

    def move_ship(self, ship):
        order = ship.orders.first()  # this is the current order
        if not order:
            return ship
        if order.target_star:
            x = order.target_star.x
            y = order.target_star.y
        elif order.target_ship:
            x = order.target_ship.x
            y = order.target_ship.y
        elif order.x and order.y:
            x = order.x
            y = order.y
        else:
            raise Exception("invalid order %s" % (str(order.id)))

        target = nparray([x, y])
        position = nparray([ship.x, ship.y])
        vector = target - position
        distance = linalg.norm(vector)
        print("position: %s" % (str(position)))
        print("target:   %s" % (str(target)))
        print("vector:   %s" % (str(vector)))
        print("distance: %s" % (str(distance)))
        if int(distance) <= order.warpfactor:
            ship.x = x
            ship.y = y
            if order.repeat:
                # this may not work....
                neworder = order
                neworder.id = None
                neworder.save()
            order.delete()
        else:
            normalised_vector = vector / distance
            print("normal:   %s" % (str(normalised_vector)))
            new_position = position + (normalised_vector * order.warpfactor)
            ship.x = int(new_position[0])
            ship.y = int(new_position[1])
        return ship

    def clear_empty_planets(self):
        """Remove ownership from planets with zero population."""
        self.game.stars.filter(colonists=0).update(player=None)

    def check_join_deadline(self):
        """Close joining if past the deadline year."""
        if self.game.join_until_year and self.game.year >= self.game.join_until_year:
            self.game.joinable = False
