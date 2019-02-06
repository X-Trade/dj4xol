from .models import Game
import numpy as np


class GameTurn:
    def __init__(self, game):
        self.game = game

    def generate(self):
        self._ship_movements()

    def generate_turns(self, turns):
        for _ in range(turns):
            self.generate()

    def _ship_movements(self):
        for ship in self.game.ships.all():
            order = ship.orders.first()  # this is the current order
            if not order:
                continue
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

            target = np.array([x, y])
            position = np.array([ship.x, ship.y])
            vector = target - position
            distance = np.linalg.norm(vector)
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
            ship.save()
