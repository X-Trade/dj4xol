from dj4xol.models import Ship, Star

from itertools import chain


class DetailBuilder():
    game = None
    selected_obj = None
    at_cursor = []
    x = None
    y = None

    def __init__(self, game, x=None, y=None, selected=None):
        self.game = game
        self.set_coordinates(x, y)
        self.find(x, y, selected)
    
    def set_coordinates(self, x, y):
        self.x = x
        self.y = y

    def find(self, x, y, selected):
        if x and y:
            self.find_all_at_coordinates(x, y)
        if selected:
            self.process_selected(selected)
        else:
            self.find_selected_from_coordinates(x, y)
        self.check_selected()

    def build_detail(self):
        if self.selected_obj:
            detail = {'name': self.get_object_name(),
                     'player': self.get_object_player(),
                     'environmentals': self.build_environmental_detail(),
                     'resources': self.build_resource_detail(),
                     'also_here': {mapobject.name: str(mapobject) for mapobject in self.at_cursor if mapobject != self.selected_obj}
                     }
        else:
            detail = None
        return detail

    def get_object_name(self):
        print(self.selected_obj.name)
        if self.selected_obj.name is None or len(self.selected_obj.name) == 0:
            return "%s %i" % (self.selected_obj.__class__.__name__, self.selected_obj.id)
        return self.selected_obj.name

    def get_object_player(self):
        if self.selected_obj.player:
            selected_obj_player = self.selected_obj.player.django_user.username
        else:
            selected_obj_player = None
        return selected_obj_player

    def find_all_at_coordinates(self, x, y):
        x = int(x)
        y = int(y)
        stars = self.game.stars.filter(x=x, y=y).all()
        ships = self.game.ships.filter(x=x, y=y).all()
        self.at_cursor = list(chain(stars, ships))
        return self.at_cursor
    
    def find_selected_from_coordinates(self, x, y):
        try:
           self.selected_obj = self.at_cursor[0]
        except IndexError:
            self.selected_obj = None
        return self.selected_obj

    def process_selected(self, selected):
        if selected:
            selected_name = selected.split(':')[1].lower()
            selected_id = int(''.join(filter(str.isdigit, selected_name)))
            selected_type = selected_name.split(str(selected_id)[:1])[0]
            if selected_type == 'star':
                self.selected_obj = Star.objects.get(pk=selected_id)
            elif selected_type == 'ship':
                self.selected_obj = Ship.objects.get(pk=selected_id)
            self.check_selected()
        return self.selected_obj

    def check_selected(self):
        if self.selected_obj and self.selected_obj.game != self.game:
            self.selected_obj = None
            raise Exception("Selected object is not in this game")
    
    def build_environmental_detail(self):
        environmentals = None
        if self.selected_obj and isinstance(self.selected_obj, Star):
            environmentals = {'Temperature': self.selected_obj.temperature,
                              'Gravity': self.selected_obj.gravity,
                              'Radiation': self.selected_obj.radiation
                             }
        return environmentals
    
    def build_resource_detail(self):
        resources = None
        if self.selected_obj and isinstance(self.selected_obj, Star):
            resources = {'Ironium': self.selected_obj.ironium,
                         'Boranium': self.selected_obj.boranium,
                         'Germanium': self.selected_obj.germanium,
                         'Colonists': self.selected_obj.colonists,
                        }
        return resources
