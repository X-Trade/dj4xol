from dj4xol.models import Ship, Star
from dj4xol.turn import calculate_growth_factor, apply_population_change, effective_capacity

from itertools import chain


class DetailBuilder():
    game = None
    player = None
    selected_obj = None
    at_cursor = []
    x = None
    y = None

    def __init__(self, game, x=None, y=None, selected=None, player=None):
        self.game = game
        self.player = player
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
                     'population': self.get_population(),
                     'population_change': self.get_population_change(),
                     'capacity': self.get_effective_capacity(),
                     'environmentals': self.build_environmental_detail(),
                     'resources': self.build_resource_detail(),
                     'also_here': {mapobject.name: str(mapobject) for mapobject in self.at_cursor if mapobject != self.selected_obj},
                     'is_star': isinstance(self.selected_obj, Star),
                     'star_id': self.selected_obj.id if isinstance(self.selected_obj, Star) else None,
                     }
        else:
            detail = None
        return detail

    def get_population(self):
        if self.selected_obj and isinstance(self.selected_obj, Star):
            return self.selected_obj.colonists
        return None

    def get_population_change(self):
        """Calculate expected population change for player-owned worlds."""
        if not self.selected_obj or not isinstance(self.selected_obj, Star):
            return None
        if not self.player or self.selected_obj.player != self.player:
            return None
        if self.selected_obj.colonists == 0:
            return None
        factor = calculate_growth_factor(self.player, self.selected_obj)
        factor *= self.player.race_type.population_growth_multiplier
        current = self.selected_obj.colonists
        new_pop = apply_population_change(current, factor)
        return new_pop - current

    def get_effective_capacity(self):
        """Get effective carrying capacity for player-owned worlds."""
        if not self.selected_obj or not isinstance(self.selected_obj, Star):
            return None
        if not self.player:
            return None
        return effective_capacity(self.player, self.selected_obj)

    def get_object_name(self):
        print(self.selected_obj.name)
        if self.selected_obj.name is None or len(self.selected_obj.name) == 0:
            return "%s %i" % (self.selected_obj.__class__.__name__, self.selected_obj.id)
        return self.selected_obj.name

    def get_object_player(self):
        """Return player display string as 'username (race name)' or None."""
        player = self.selected_obj.player
        if player:
            username = player.account.alias if player.account else 'Unknown'
            return '%s (%s)' % (username, player.name)
        return None

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
            # Model values are 0.0-2.0, where 1.0 = 100% (average)
            # 0.0 = 0%, 2.0 = 200%
            grav = self.selected_obj.gravity
            temp = self.selected_obj.temperature
            rad = self.selected_obj.radiation
            environmentals = {
                'Gravity': self._build_env_data('gravity', grav, '%.2fg' % grav),
                'Temperature': self._build_env_data('temperature', temp, '%+d°C' % int((temp - 1.0) * 100)),
                'Radiation': self._build_env_data('radiation', rad, '%dmR' % int(rad * 50)),
            }
        return environmentals

    def _build_env_data(self, env_name, value, display):
        """Build environmental data dict with habitability range if player available."""
        data = {
            'value': value,
            'display': display,
            'percent': (value / 2.0) * 100
        }
        if self.player:
            hab_min = self.player.hab_min(env_name)
            hab_max = self.player.hab_max(env_name)
            center = getattr(self.player, f'{env_name}_center')
            data['hab_min_percent'] = (hab_min / 2.0) * 100
            data['hab_max_percent'] = (hab_max / 2.0) * 100
            data['hab_center_percent'] = (center / 2.0) * 100
            data['is_habitable'] = hab_min <= value <= hab_max
        return data
    
    def build_resource_detail(self):
        resources = None
        if self.selected_obj and isinstance(self.selected_obj, Star):
            resources = {'Ironium': self.selected_obj.ironium,
                         'Boranium': self.selected_obj.boranium,
                         'Germanium': self.selected_obj.germanium,
                        }
        return resources
