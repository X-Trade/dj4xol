from dj4xol.models import Fleet, Star
from dj4xol.turn import calculate_growth_factor, apply_population_change, effective_capacity, calculate_employment_percent, COLONISTS_PER_JOB

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
        if selected:
            # sel parameter takes priority - find the object first
            self.process_selected(selected)
            # Then find all objects at the selected object's actual location
            if self.selected_obj:
                self.find_all_at_coordinates(self.selected_obj.x, self.selected_obj.y)
        elif x and y:
            # Fall back to x & y coordinates if no sel parameter
            self.find_all_at_coordinates(x, y)
            self.find_selected_from_coordinates(x, y)
        self.check_selected()

    def build_detail(self):
        if self.selected_obj:
            detail = {'name': self.get_object_name(),
                     'selected_id': self.selected_obj.short_id,
                     'objects_here': self.get_objects_here(),
                     'player': self.get_object_player(),
                     'is_owned': self.selected_obj.player == self.player if self.player else False,
                     'population': self.get_population(),
                     'population_change': self.get_population_change(),
                     'capacity': self.get_effective_capacity(),
                     'environmentals': self.build_environmental_detail(),
                     'resources': self.build_resource_detail(),
                     'infrastructure': self.build_infrastructure_detail(),
                     'is_star': isinstance(self.selected_obj, Star),
                     'is_fleet': isinstance(self.selected_obj, Fleet),
                     'star_short_id': self.selected_obj.short_id if isinstance(self.selected_obj, Star) else None,
                     'fleet_short_id': self.selected_obj.short_id if isinstance(self.selected_obj, Fleet) else None,
                     'production_orders': self.get_production_orders(),
                     'fleet_orders': self.get_fleet_orders(),
                     'fleet_cargo': self.get_fleet_cargo(),
                     'fleet_inventory': self.build_fleet_inventory(),
                     'x': self.selected_obj.x,
                     'y': self.selected_obj.y,
                     }
        else:
            detail = None
        return detail

    def get_objects_here(self):
        """Return list of (name, short_id) dicts for all objects at cursor."""
        result = []
        for obj in self.at_cursor:
            name = obj.name or f"{obj.__class__.__name__} {obj.id}"
            result.append({'name': name, 'id': obj.short_id})
        return result

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
        if self.selected_obj.name is None or len(self.selected_obj.name) == 0:
            return "%s %i" % (self.selected_obj.__class__.__name__, self.selected_obj.id)
        return self.selected_obj.name

    def get_object_player(self):
        """Return player display string as 'race name (username)' or None."""
        player = self.selected_obj.player
        if player:
            username = player.account.alias if player.account else 'Unknown'
            return '%s (%s)' % (player.name, username)
        return None

    def find_all_at_coordinates(self, x, y):
        x = int(x)
        y = int(y)
        stars = self.game.stars.filter(x=x, y=y).all()
        fleets = self.game.fleets.filter(x=x, y=y).all()
        self.at_cursor = list(chain(stars, fleets))
        return self.at_cursor

    def find_selected_from_coordinates(self, x, y):
        try:
           self.selected_obj = self.at_cursor[0]
        except IndexError:
            self.selected_obj = None
        return self.selected_obj

    def process_selected(self, selected):
        if selected:
            short_id = selected.lower()
            self.selected_obj = (
                Star.objects.filter(game=self.game, short_id=short_id).first() or
                Fleet.objects.filter(game=self.game, short_id=short_id).first()
            )
            if self.selected_obj:
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
            resources = {
                'Ironium': {
                    'yield': self.selected_obj.ironium,
                    'surface': self.selected_obj.ironium_surface,
                },
                'Boranium': {
                    'yield': self.selected_obj.boranium,
                    'surface': self.selected_obj.boranium_surface,
                },
                'Germanium': {
                    'yield': self.selected_obj.germanium,
                    'surface': self.selected_obj.germanium_surface,
                },
            }
        return resources

    def build_infrastructure_detail(self):
        infrastructure = None
        if self.selected_obj and isinstance(self.selected_obj, Star):
            jobs = (self.selected_obj.mines + self.selected_obj.factories + self.selected_obj.defenses) * COLONISTS_PER_JOB
            employment = calculate_employment_percent(self.selected_obj)
            infrastructure = {
                'Mines': self.selected_obj.mines,
                'Factories': self.selected_obj.factories,
                'Defenses': self.selected_obj.defenses,
                'Jobs': {'count': jobs, 'employment': employment},
            }
        return infrastructure

    def get_production_orders(self):
        """Get production orders for selected star."""
        from .models import PRODUCTION_COSTS
        if not self.selected_obj or not isinstance(self.selected_obj, Star):
            return []
        if not self.player or self.selected_obj.player != self.player:
            return []
        orders = []
        for o in self.selected_obj.production_orders.order_by('position'):
            cost = PRODUCTION_COSTS.get(o.order_type, {})
            
            # Calculate progress based on what has actually been spent
            labor_cost = cost.get('bp', 0)
            resource_cost = cost.get('ironium', 0) + cost.get('boranium', 0) + cost.get('germanium', 0)
            
            if labor_cost > 0 and resource_cost > 0:
                # Items with both labor and resources: each contributes 50%
                resource_progress = min(
                    (o.spent_ironium + o.spent_boranium + o.spent_germanium) / resource_cost * 50, 50
                )
                labor_progress = min(o.spent_bp / labor_cost * 50, 50)
                total_progress = resource_progress + labor_progress
            elif labor_cost > 0:
                # Labor only: contributes 100%
                resource_progress = 0
                labor_progress = min(o.spent_bp / labor_cost * 100, 100)
                total_progress = labor_progress
            elif resource_cost > 0:
                # Resources only: contribute 100%
                resource_progress = min(
                    (o.spent_ironium + o.spent_boranium + o.spent_germanium) / resource_cost * 100, 100
                )
                labor_progress = 0
                total_progress = resource_progress
            else:
                # No costs (shouldn't happen)
                resource_progress = labor_progress = total_progress = 0
            
            orders.append({
                'short_id': o.short_id,
                'type': o.order_type,
                'display': o.get_order_type_display(),
                'quantity': o.quantity,
                'completed': o.completed,
                'repeat': o.repeat,
                'progress_percent': min(int(total_progress), 100),
                'resource_progress': min(int(resource_progress), 50 if labor_cost > 0 and resource_cost > 0 else 100),
                'labor_progress': min(int(labor_progress), 50 if resource_cost > 0 and labor_cost > 0 else 100),
                'has_labor': labor_cost > 0,
                'cost': {
                    'bp': cost.get('bp', 0),
                    'ironium': cost.get('ironium', 0),
                    'boranium': cost.get('boranium', 0),
                    'germanium': cost.get('germanium', 0),
                    'colonists': cost.get('colonists', 0),
                },
                'spent': {
                    'bp': o.spent_bp,
                    'ironium': o.spent_ironium,
                    'boranium': o.spent_boranium,
                    'germanium': o.spent_germanium,
                },
                'remaining': {
                    'bp': cost.get('bp', 0) - o.spent_bp,
                    'ironium': cost.get('ironium', 0) - o.spent_ironium,
                    'boranium': cost.get('boranium', 0) - o.spent_boranium,
                    'germanium': cost.get('germanium', 0) - o.spent_germanium,
                },
            })
        return orders

    def get_fleet_orders(self):
        """Get movement orders for selected fleet."""
        if not self.selected_obj or not isinstance(self.selected_obj, Fleet):
            return []
        if not self.player or self.selected_obj.player != self.player:
            return []
        orders = []
        for o in self.selected_obj.orders.all():
            target = None
            if o.target_star:
                target = o.target_star.name
            elif o.target_fleet:
                target = o.target_fleet.name
            elif o.x is not None and o.y is not None:
                target = f"Empty Space ({o.x}, {o.y})"
            orders.append({
                'short_id': o.short_id,
                'target': target,
                'warpfactor': o.warpfactor,
                'repeat': o.repeat,
                'order_type': o.order_type,
                'transfer_type': o.transfer_type,
                'transfer_ironium': o.transfer_ironium,
                'transfer_boranium': o.transfer_boranium,
                'transfer_germanium': o.transfer_germanium,
                'transfer_colonists': o.transfer_colonists,
                'target_star': o.target_star,  # For template access
            })
        return orders

    def get_fleet_cargo(self):
        """Get cargo details for selected fleet."""
        if not self.selected_obj or not isinstance(self.selected_obj, Fleet):
            return None
        if not self.player or self.selected_obj.player != self.player:
            return None
        
        return {
            'capacity': self.selected_obj.cargo_capacity,
            'used': self.selected_obj.cargo_used,
            'remaining': self.selected_obj.cargo_remaining,
            'ironium': self.selected_obj.ironium,
            'boranium': self.selected_obj.boranium,
            'germanium': self.selected_obj.germanium,
            'colonists': self.selected_obj.colonists,
        }

    def build_fleet_inventory(self):
        """Build fleet cargo inventory data for progress bar display."""
        if not self.selected_obj or not isinstance(self.selected_obj, Fleet):
            return None
        if not self.player or self.selected_obj.player != self.player:
            return None
        
        capacity = self.selected_obj.cargo_capacity
        inventory = {
            'Ironium': self._build_cargo_data(self.selected_obj.ironium, capacity, 'kt'),
            'Boranium': self._build_cargo_data(self.selected_obj.boranium, capacity, 'kt'),
            'Germanium': self._build_cargo_data(self.selected_obj.germanium, capacity, 'kt'),
            'Colonists': self._build_cargo_data(self.selected_obj.colonists, capacity, 'k'),
        }
        return inventory

    def _build_cargo_data(self, amount, capacity, unit):
        """Build cargo data dict for progress bar display."""
        percent = (amount / capacity * 100) if capacity > 0 else 0
        return {
            'amount': amount,
            'percent': percent,
            'display': f'{amount:,}{unit}',
        }
