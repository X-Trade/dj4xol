from django.db import models
from dj4xol.models import Fleet, Star, Salvage, Report
from dj4xol.turn import apply_population_change, KT_PER_MINE
from dj4xol.research import get_player_colony_defense_level
from dj4xol.colony_rules import (
    calculate_growth_factor,
    calculate_habitability_factor,
    effective_capacity,
    calculate_employment_percent,
    calculate_effective_defenses,
    calculate_available_buildpoints,
    calculate_available_researchpoints,
    calculate_staffing_ratio,
    calculate_productivity_multiplier,
    COLONISTS_PER_JOB,
    COLONISTS_PER_SHIPYARD,
)

from itertools import chain
from math import ceil, sqrt


class DetailBuilder():
    game = None
    player = None
    selected_obj = None
    at_cursor = []
    x = None
    y = None

    @staticmethod
    def format_empty_space(x, y):
        """Format empty space coordinates consistently across the UI."""
        return f"Empty Space ({x}, {y})"

    @staticmethod
    def format_kt(value):
        """Format a resource value with commas and kt suffix."""
        return f"{value:,}kt"

    @staticmethod
    def _estimate_eta_years(start_x, start_y, target_x, target_y, warp):
        """Estimate years to reach target at a constant warp speed."""
        if start_x is None or start_y is None or target_x is None or target_y is None:
            return None
        dx = int(target_x) - int(start_x)
        dy = int(target_y) - int(start_y)
        distance = sqrt((dx * dx) + (dy * dy))
        if distance <= 0:
            return 0
        speed = max(0, int(warp or 0))
        if speed <= 0:
            return None
        return max(1, int(ceil(distance / float(speed))))

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
            can_view, report_year = self.can_view_object(self.selected_obj)

            if not can_view:
                # Return unexplored placeholder
                return {
                    'name': self.get_object_name(),
                    'selected_id': self.selected_obj.short_id,
                    'objects_here': self.get_objects_here(),
                    'unexplored': True,
                    'x': self.selected_obj.x,
                    'y': self.selected_obj.y,
                    'is_star': isinstance(self.selected_obj, Star),
                    'is_fleet': isinstance(self.selected_obj, Fleet),
                    'is_salvage': isinstance(self.selected_obj, Salvage),
                }

            if report_year is not None:
                # Load from cached report
                return self._build_detail_from_report(report_year)

            # Current data (owned or fleet present)
            detail = {'name': self.get_object_name(),
                     'selected_id': self.selected_obj.short_id,
                     'objects_here': self.get_objects_here(),
                     'player': self.get_object_player(),
                     'is_owned': self.selected_obj.player == self.player if self.player else False,
                     'is_survivable': self.get_survivability(),
                     'population': self.get_population(),
                     'population_change': self.get_population_change(),
                     'capacity': self.get_effective_capacity(),
                     'environmentals': self.build_environmental_detail(),
                     'resources': self.build_resource_detail(),
                     'infrastructure': self.build_infrastructure_detail(),
                     'is_star': isinstance(self.selected_obj, Star),
                     'is_fleet': isinstance(self.selected_obj, Fleet),
                     'is_salvage': isinstance(self.selected_obj, Salvage),
                     'fleet_thumbnail': (
                         self.selected_obj.effective_thumbnail_path
                         if isinstance(self.selected_obj, Fleet) else None
                     ),
                     'star_thumbnail': (
                         self.selected_obj.effective_thumbnail_path
                         if isinstance(self.selected_obj, Star) else None
                     ),
                     'star_short_id': self.selected_obj.short_id if isinstance(self.selected_obj, Star) else None,
                     'fleet_short_id': self.selected_obj.short_id if isinstance(self.selected_obj, Fleet) else None,
                     'salvage_short_id': self.selected_obj.short_id if isinstance(self.selected_obj, Salvage) else None,
                     'salvage_inventory': self.build_salvage_inventory(),
                     'production_orders': self.get_production_orders(),
                     'fleet_orders': self.get_fleet_orders(),
                     'fleet_cargo': self.get_fleet_cargo(),
                     'fleet_inventory': self.build_fleet_inventory(),
                     'transfer_targets': self.get_transfer_targets(),
                     'colonise_targets': self.get_colonise_targets(),
                     'bomb_targets': self.get_bomb_targets(),
                     'remotemine_targets': self.get_remotemine_targets(),
                     'merge_targets': self.get_merge_targets(),
                     'patrol_targets': self.get_patrol_targets(),
                     'effective_location': self.get_fleet_effective_location() if isinstance(self.selected_obj, Fleet) else None,
                     'x': self.selected_obj.x,
                     'y': self.selected_obj.y,
                     'report_year': None,
                     'is_current': True,
                     }
            if detail['effective_location']:
                effective_x, effective_y = detail['effective_location']
                detail['effective_location_name'] = self.format_empty_space(effective_x, effective_y)
        else:
            detail = None
        return detail

    def _build_detail_from_report(self, report_year):
        """Build detail dict from a cached report."""
        target_type = self._get_target_type(self.selected_obj)
        report = Report.objects.get(
            player=self.player,
            target_type=target_type,
            target_id=self.selected_obj.id
        )
        data = report.get_report_data()

        # Base detail fields
        detail = {
            'name': data.get('name', self.get_object_name()),
            'selected_id': self.selected_obj.short_id,
            'objects_here': self.get_objects_here(),
            'x': data.get('x', self.selected_obj.x),
            'y': data.get('y', self.selected_obj.y),
            'is_star': target_type == 'star',
            'is_fleet': target_type == 'fleet',
            'is_salvage': target_type == 'salvage',
            'fleet_thumbnail': (
                self.selected_obj.effective_thumbnail_path if target_type == 'fleet' else None
            ),
            'star_thumbnail': (
                self.selected_obj.effective_thumbnail_path if target_type == 'star' else None
            ),
            'report_year': report_year,
            'report_age': self.game.year - report_year,
            'is_current': False,
            'is_owned': False,
        }

        # Add player name from cached data
        if data.get('player_name'):
            detail['player'] = data['player_name']

        # Type-specific fields from cached report
        if target_type == 'star':
            detail['star_short_id'] = self.selected_obj.short_id
            detail['population'] = data.get('colonists')
            detail['capacity'] = data.get('capacity')
            detail['is_survivable'] = data.get('is_survivable')
            if all(k in data for k in [
                'ironium_yield', 'boranium_yield', 'germanium_yield',
                'ironium_inventory', 'boranium_inventory', 'germanium_inventory',
            ]):
                detail['resources'] = {
                    'Ironium': {
                        'yield': data['ironium_yield'],
                        'surface': data['ironium_inventory'],
                        'mining_rate': 0,
                    },
                    'Boranium': {
                        'yield': data['boranium_yield'],
                        'surface': data['boranium_inventory'],
                        'mining_rate': 0,
                    },
                    'Germanium': {
                        'yield': data['germanium_yield'],
                        'surface': data['germanium_inventory'],
                        'mining_rate': 0,
                    },
                }
            # Build environmental detail from cached data
            if all(k in data for k in ['gravity', 'temperature', 'radiation']):
                detail['environmentals'] = self._build_env_from_report(data)
                if detail['is_survivable'] is None:
                    detail['is_survivable'] = self._is_survivable_from_report(data)
            if all(k in data for k in [
                'mines', 'factories', 'factories_bp', 'labs', 'labs_rp',
                'defenses', 'shipyards',
            ]):
                detail['infrastructure'] = {
                    'Mines': data.get('mines'),
                    'Factories': data.get('factories'),
                    'FactoriesBP': data.get('factories_bp'),
                    'Labs': data.get('labs'),
                    'LabsRP': data.get('labs_rp'),
                    'Defenses': data.get('defenses'),
                    'DefensesTooltip': data.get('defenses_tooltip'),
                    'Shipyards': data.get('shipyards'),
                    'Jobs': {
                        'count': data.get('jobs_count', 0),
                        'employment': data.get('jobs_employment', 0.0),
                    },
                }
        elif target_type == 'fleet':
            detail['fleet_short_id'] = self.selected_obj.short_id
            if 'ship_count' in data:
                detail['fleet_cargo'] = {
                    'ship_count': data.get('ship_count'),
                    'max_safe_warp': data.get('max_safe_warp'),
                    'integrity': data.get('integrity'),
                    'offense_modifier': data.get('offense_modifier'),
                    'defense_modifier': data.get('defense_modifier'),
                    'has_bombs': data.get('has_bombs'),
                    'has_miners': data.get('has_miners'),
                    'has_fuel_factory': data.get('has_fuel_factory'),
                    'has_wormhole_drive': data.get('has_wormhole_drive'),
                }
        elif target_type == 'salvage':
            detail['salvage_short_id'] = self.selected_obj.short_id
            if 'total_minerals' in data:
                detail['salvage_inventory'] = {
                    'ironium': data.get('ironium_inventory', 0),
                    'boranium': data.get('boranium_inventory', 0),
                    'germanium': data.get('germanium_inventory', 0),
                    'total': data['total_minerals'],
                }

        return detail

    def _build_env_from_report(self, data):
        """Build environmental detail dict from cached report data."""
        grav = data['gravity']
        temp = data['temperature']
        rad = data['radiation']
        return {
            'Gravity': self._build_env_data('gravity', grav, '%.2fg' % grav),
            'Temperature': self._build_env_data(
                'temperature', temp, '%+d°C' % int((temp - 1.0) * 100)
            ),
            'Radiation': self._build_env_data(
                'radiation', rad, '%dmR' % int(rad * 50)
            ),
        }

    def get_objects_here(self):
        """Return list of dicts with name, short_id, and type for all objects at cursor."""
        result = []
        for obj in self.at_cursor:
            name = obj.name or f"{obj.__class__.__name__} {obj.id}"
            if isinstance(obj, Star):
                obj_type = 'star'
            elif isinstance(obj, Fleet):
                obj_type = 'fleet'
            elif isinstance(obj, Salvage):
                obj_type = 'salvage'
            else:
                obj_type = 'unknown'
            result.append({
                'name': name,
                'short_id': obj.short_id,
                'type': obj_type
            })
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

    def get_survivability(self):
        """Return whether colonists can survive on this star for this player."""
        if not self.selected_obj or not isinstance(self.selected_obj, Star):
            return None
        if not self.player:
            return None
        return calculate_habitability_factor(self.player, self.selected_obj) >= 0

    def _is_survivable_from_report(self, data):
        """Return survivability from cached environmental report data."""
        if not self.player:
            return None
        for env in ['gravity', 'temperature', 'radiation']:
            if env not in data:
                return None

        report_star = type('ReportStar', (), {
            'gravity': data['gravity'],
            'temperature': data['temperature'],
            'radiation': data['radiation'],
            # Cached reports do not include infrastructure economy context.
            'colonists': data.get('colonists', 0),
            'mines': data.get('mines', 0),
            'factories': data.get('factories', 0),
            'labs': data.get('labs', 0),
            'defenses': data.get('defenses', 0),
            'shipyards': data.get('shipyards', 0),
            'buildpoints_consumed': data.get('buildpoints_consumed', 0),
        })()
        return calculate_habitability_factor(self.player, report_star) >= 0

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
        salvages = self.game.salvages.filter(x=x, y=y).all()
        self.at_cursor = list(chain(stars, fleets, salvages))
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
                Fleet.objects.filter(game=self.game, short_id=short_id).first() or
                Salvage.objects.filter(game=self.game, short_id=short_id).first()
            )
            if self.selected_obj:
                self.check_selected()
        return self.selected_obj

    def check_selected(self):
        if self.selected_obj and self.selected_obj.game != self.game:
            self.selected_obj = None
            raise Exception("Selected object is not in this game")

    def can_view_object(self, obj):
        """Check if player can view object details.

        Returns tuple: (can_view, report_year or None)
        - can_view=True, year=None means current data (owned or fleet present)
        - can_view=True, year=N means cached report from year N
        - can_view=False, year=None means unexplored
        """
        if not self.player:
            return (False, None)

        # Player owns the object
        if hasattr(obj, 'player') and obj.player == self.player:
            return (True, None)

        # Player has a fleet at the location
        player_fleets_here = Fleet.objects.filter(
            game=self.game,
            player=self.player,
            x=obj.x,
            y=obj.y
        ).exists()
        if player_fleets_here:
            return (True, None)

        # Player owns a star at the location
        player_star_here = Star.objects.filter(
            game=self.game,
            player=self.player,
            x=obj.x,
            y=obj.y
        ).exists()
        if player_star_here:
            return (True, None)

        # Player has a cached report
        target_type = self._get_target_type(obj)
        report = Report.objects.filter(
            player=self.player,
            target_type=target_type,
            target_id=obj.id
        ).first()
        if report:
            return (True, report.year)

        return (False, None)

    def _get_target_type(self, obj):
        """Get target_type string for an object."""
        if isinstance(obj, Star):
            return 'star'
        elif isinstance(obj, Fleet):
            return 'fleet'
        elif isinstance(obj, Salvage):
            return 'salvage'
        return 'unknown'

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
            mining_rates = self._build_resource_mining_rates()
            resources = {
                'Ironium': {
                    'yield': self.selected_obj.ironium_yield,
                    'surface': self.selected_obj.ironium_inventory,
                    'mining_rate': mining_rates['ironium'],
                },
                'Boranium': {
                    'yield': self.selected_obj.boranium_yield,
                    'surface': self.selected_obj.boranium_inventory,
                    'mining_rate': mining_rates['boranium'],
                },
                'Germanium': {
                    'yield': self.selected_obj.germanium_yield,
                    'surface': self.selected_obj.germanium_inventory,
                    'mining_rate': mining_rates['germanium'],
                },
            }
        return resources

    def _build_resource_mining_rates(self):
        """Build per-resource expected mining output for one year."""
        rates = {'ironium': 0, 'boranium': 0, 'germanium': 0}
        if not self.selected_obj or not isinstance(self.selected_obj, Star):
            return rates
        if not self.player or self.selected_obj.player != self.player:
            return rates

        star = self.selected_obj
        total_yield = (
            star.ironium_yield + star.boranium_yield + star.germanium_yield
        )
        if total_yield <= 0 or star.mines <= 0:
            return rates

        staffing_ratio = calculate_staffing_ratio(star)
        if staffing_ratio <= 0:
            return rates

        productivity = calculate_productivity_multiplier(staffing_ratio)
        total_extraction = star.mines * KT_PER_MINE * productivity

        rates['ironium'] = int(total_extraction * star.ironium_yield / total_yield)
        rates['boranium'] = int(total_extraction * star.boranium_yield / total_yield)
        rates['germanium'] = int(
            total_extraction * star.germanium_yield / total_yield
        )
        return rates

    def build_infrastructure_detail(self):
        infrastructure = None
        if self.selected_obj and isinstance(self.selected_obj, Star):
            is_owned = (
                self.player is not None and self.selected_obj.player == self.player
            )
            jobs = ((self.selected_obj.mines + self.selected_obj.factories
                     + self.selected_obj.labs
                     + self.selected_obj.defenses) * COLONISTS_PER_JOB
                    + self.selected_obj.shipyards * COLONISTS_PER_SHIPYARD)
            employment = calculate_employment_percent(self.selected_obj)
            defenses_tooltip = None
            if is_owned:
                colony_defense_level = get_player_colony_defense_level(self.player)
                defense_multiplier = 2.0 ** max(0.0, colony_defense_level)
                effective_base_defenses = calculate_effective_defenses(
                    self.selected_obj
                )
                effective_defenses = int(
                    effective_base_defenses * defense_multiplier
                )
                modifier = int(round(colony_defense_level * 10.0))
                defenses_tooltip = f"{effective_defenses}({modifier:+d})"
            infrastructure = {
                'Mines': self.selected_obj.mines,
                'Factories': self.selected_obj.factories,
                'FactoriesBP': calculate_available_buildpoints(self.selected_obj),
                'Labs': self.selected_obj.labs,
                'LabsRP': calculate_available_researchpoints(self.selected_obj),
                'Defenses': self.selected_obj.defenses,
                'DefensesTooltip': defenses_tooltip,
                'Shipyards': self.selected_obj.shipyards,
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
                    'ironium': self.format_kt(o.spent_ironium),
                    'boranium': self.format_kt(o.spent_boranium),
                    'germanium': self.format_kt(o.spent_germanium),
                },
                'remaining': {
                    'bp': cost.get('bp', 0) - o.spent_bp,
                    'ironium': self.format_kt(cost.get('ironium', 0) - o.spent_ironium),
                    'boranium': self.format_kt(cost.get('boranium', 0) - o.spent_boranium),
                    'germanium': self.format_kt(cost.get('germanium', 0) - o.spent_germanium),
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
        current_x = int(self.selected_obj.x)
        current_y = int(self.selected_obj.y)
        for o in self.selected_obj.orders.order_by('position', 'id'):
            target = None
            target_link = None
            obj, x, y, kind = o.get_actual_target()
            eta_years = None
            if kind in ['star', 'fleet', 'salvage'] and obj:
                target = obj.name
                target_link = f'?x={obj.x}&y={obj.y}&sel={obj.short_id}&locate=1'
            elif kind == 'space':
                target = DetailBuilder.format_empty_space(x, y)
                if x is not None and y is not None:
                    target_link = f'?x={x}&y={y}&locate=1'

            if o.order_type in ['MOVE', 'INTERCEPT', 'PATROL']:
                eta_years = self._estimate_eta_years(
                    current_x,
                    current_y,
                    x,
                    y,
                    o.warpfactor,
                )

            if o.order_type in ['MOVE', 'INTERCEPT', 'PATROL'] and x is not None and y is not None:
                current_x = int(x)
                current_y = int(y)
            repeat_allowed = o.order_type not in ['COLONISE', 'MERGE', 'SCUTTLE']
            orders.append({
                'short_id': o.short_id,
                'target': target,
                'target_link': target_link,
                'warpfactor': o.warpfactor,
                'eta_years': eta_years,
                'repeat': o.repeat,
                'repeat_allowed': repeat_allowed,
                'order_type': o.order_type,
                'patrol_radius': o.patrol_radius,
                'transfer_type': o.transfer_type,
                'transfer_ironium': o.transfer_ironium,
                'transfer_boranium': o.transfer_boranium,
                'transfer_germanium': o.transfer_germanium,
                'transfer_colonists': o.transfer_colonists,
                'target_star': o.target_star,  # For template access
                'target_salvage': o.target_salvage,  # For template access
            })
        return orders

    def get_fleet_cargo(self):
        """Get cargo details for selected fleet."""
        if not self.selected_obj or not isinstance(self.selected_obj, Fleet):
            return None

        # Always expose composition for visible fleets (own or observed).
        # Cargo/inventory remains owner-only.
        cargo = self._build_fleet_composition(self.selected_obj)
        if self.player and self.selected_obj.player == self.player:
            cargo.update({
                'capacity': self.selected_obj.cargo_capacity,
                'used': self.selected_obj.cargo_used,
                'remaining': self.selected_obj.cargo_remaining,
                'fuel': self.selected_obj.fuel,
                'max_fuel': self.selected_obj.max_fuel,
                'ironium': self.selected_obj.ironium_inventory,
                'boranium': self.selected_obj.boranium_inventory,
                'germanium': self.selected_obj.germanium_inventory,
                'colonists': self.selected_obj.colonists,
            })
        return cargo

    def _build_fleet_composition(self, fleet):
        """Build non-cargo fleet composition fields."""
        offense_mod = int(round(float(fleet.offense_level) * 10.0))
        defense_mod = int(round(float(fleet.defense_level) * 10.0))
        return {
            'max_safe_warp': fleet.max_safe_warp,
            'integrity': fleet.integrity,
            'ship_count': fleet.ship_count,
            'offense_modifier': f'{offense_mod:+d}',
            'defense_modifier': f'{defense_mod:+d}',
            'has_bombs': fleet.has_bombs,
            'has_miners': fleet.has_miners,
            'has_fuel_factory': bool(fleet.has_fuel_factory),
            'has_wormhole_drive': bool(fleet.has_wormhole_drive),
        }

    def build_fleet_inventory(self):
        """Build fleet cargo inventory data for progress bar display."""
        if not self.selected_obj or not isinstance(self.selected_obj, Fleet):
            return None
        if not self.player or self.selected_obj.player != self.player:
            return None
        
        capacity = self.selected_obj.cargo_capacity
        fuel_cap = max(0.0, float(self.selected_obj.max_fuel))
        inventory = {
            'Fuel': self._build_cargo_data(self.selected_obj.fuel, fuel_cap, 'mg'),
            'Ironium': self._build_cargo_data(self.selected_obj.ironium_inventory, capacity, 'kt'),
            'Boranium': self._build_cargo_data(self.selected_obj.boranium_inventory, capacity, 'kt'),
            'Germanium': self._build_cargo_data(self.selected_obj.germanium_inventory, capacity, 'kt'),
            'Colonists': self._build_cargo_data(self.selected_obj.colonists, capacity, 'k'),
        }
        return inventory

    def _build_cargo_data(self, amount, capacity, unit):
        """Build cargo data dict for progress bar display."""
        percent = (amount / capacity * 100) if capacity > 0 else 0
        if unit == 'mg':
            display = f'{float(amount):.1f}{unit}'
        else:
            display = f'{amount:,}{unit}'
        return {
            'amount': amount,
            'percent': percent,
            'display': display,
        }

    def build_salvage_inventory(self):
        """Build salvage mineral inventory data."""
        if not self.selected_obj or not isinstance(self.selected_obj, Salvage):
            return None

        return {
            'ironium': self.selected_obj.ironium_inventory,
            'boranium': self.selected_obj.boranium_inventory,
            'germanium': self.selected_obj.germanium_inventory,
            'total': self.selected_obj.total_minerals,
        }

    def get_fleet_effective_location(self):
        """Calculate where the fleet will be after executing all current orders."""
        if not isinstance(self.selected_obj, Fleet):
            return self.selected_obj.x, self.selected_obj.y
        
        fleet = self.selected_obj
        current_x, current_y = fleet.x, fleet.y
        
        # Walk through orders to find the final destination
        orders = fleet.orders.filter(
            order_type__in=['MOVE', 'TRANSFER', 'INTERCEPT', 'PATROL']
        ).order_by('id')
        
        for order in orders:
            if order.order_type in ['MOVE', 'INTERCEPT', 'PATROL']:
                _, x, y, kind = order.get_actual_target()
                if kind in ['invalid', 'none']:
                    continue
                current_x, current_y = x, y
            elif order.order_type == 'TRANSFER':
                # Transfer orders execute at the current location but don't change it
                # (the fleet stays where it is)
                pass
        
        return current_x, current_y

    def get_destination_targets(self, x, y, selected_target=None, exclude_fleet_id=None):
        """Get available destination targets for Move/Intercept selection."""
        targets = self._build_location_targets(
            x,
            y,
            include_stars=True,
            include_fleets=True,
            include_salvage=True,
            include_empty=True,
            include_future_fleets=False,
            exclude_fleet_id=exclude_fleet_id,
            include_order_types=['MOVE', 'INTERCEPT', 'PATROL'],
        )

        if not targets:
            return {
                'targets': [],
                'location': (x, y),
                'display_mode': 'empty',
                'default_target': None,
                'selected_target': None,
            }

        if len(targets) == 1 and targets[0].get('type') == 'space':
            empty_space_name = DetailBuilder.format_empty_space(x, y)
            return {
                'targets': targets,
                'location': (x, y),
                'display_mode': 'empty',
                'default_target': empty_space_name,
                'selected_target': 'space',
            }

        selected = selected_target
        if selected:
            match = False
            for target in targets:
                target_key = f"{target['type']}:{target.get('short_id', '')}"
                if target['type'] == 'space':
                    target_key = 'space'
                if target_key == selected:
                    match = True
                    break
            if not match:
                selected = None

        if len(targets) == 1:
            target = targets[0]
            display_name = f"{target['name']} ({target['type'].title()})"
            return {
                'targets': targets,
                'location': (x, y),
                'display_mode': 'single',
                'default_target': display_name,
                'selected_target': selected or f"{target['type']}:{target.get('short_id', '')}",
            }

        return {
            'targets': targets,
            'location': (x, y),
            'display_mode': 'multiple',
            'default_target': targets[0],
            'selected_target': selected,
        }

    def _build_location_targets(
        self,
        x,
        y,
        include_stars=True,
        include_fleets=True,
        include_salvage=False,
        include_empty=False,
        include_future_fleets=False,
        fleet_player=None,
        exclude_fleet_id=None,
        include_order_types=None,
    ):
        """Collect target objects at a location with flexible filters.

        include_future_fleets adds fleets that have orders targeting this
        location or a star at this location.
        """
        targets = []
        seen = set()

        def add_target(target):
            key = (target.get('type'), target.get('short_id'))
            if key in seen:
                return
            seen.add(key)
            targets.append(target)

        stars_at_location = []
        if include_stars:
            stars_at_location = list(self.game.stars.filter(x=x, y=y))
            for star in stars_at_location:
                add_target({
                    'name': star.name,
                    'short_id': star.short_id,
                    'type': 'star',
                })

        if include_fleets:
            fleets_qs = self.game.fleets.filter(x=x, y=y)
            if fleet_player is not None:
                fleets_qs = fleets_qs.filter(player=fleet_player)
            if exclude_fleet_id is not None:
                fleets_qs = fleets_qs.exclude(id=exclude_fleet_id)
            for fleet in fleets_qs:
                add_target({
                    'name': fleet.name,
                    'short_id': fleet.short_id,
                    'type': 'fleet',
                })

        if include_future_fleets:
            from .models import FleetOrders

            order_types = include_order_types or ['MOVE']
            orders_qs = FleetOrders.objects.filter(
                game=self.game,
                order_type__in=order_types,
            )
            if fleet_player is not None:
                orders_qs = orders_qs.filter(fleet__player=fleet_player)

            target_star_filter = None
            if stars_at_location:
                target_star_filter = models.Q(target_star__in=stars_at_location)

            location_filter = models.Q(x=x, y=y)
            if target_star_filter is not None:
                orders_qs = orders_qs.filter(location_filter | target_star_filter)
            else:
                orders_qs = orders_qs.filter(location_filter)

            if exclude_fleet_id is not None:
                orders_qs = orders_qs.exclude(fleet_id=exclude_fleet_id)

            fleet_ids = {order.fleet_id for order in orders_qs}
            if fleet_ids:
                fleets_qs = self.game.fleets.filter(id__in=fleet_ids)
                if fleet_player is not None:
                    fleets_qs = fleets_qs.filter(player=fleet_player)
                for fleet in fleets_qs:
                    if exclude_fleet_id is not None and fleet.id == exclude_fleet_id:
                        continue
                    add_target({
                        'name': fleet.name,
                        'short_id': fleet.short_id,
                        'type': 'fleet',
                    })

        if include_salvage:
            for salvage in self.game.salvages.filter(x=x, y=y):
                add_target({
                    'name': salvage.name,
                    'short_id': salvage.short_id,
                    'type': 'salvage',
                    'total_minerals': salvage.total_minerals,
                })

        if include_empty and not targets:
            empty_space_name = self.format_empty_space(x, y)
            targets.append({
                'name': empty_space_name,
                'short_id': '',
                'type': 'space',
            })

        return targets
    
    def get_transfer_targets(self):
        """Get available transfer targets at the fleet's effective location.
        
        Returns a dict with:
        - targets: list of available targets
        - location: (x, y) coordinates
        - display_mode: 'single', 'multiple', or 'empty'
        - default_target: the target to select by default
        
        Includes:
        - Stars at the effective location
        - Fleets currently at the effective location 
        - Fleets that have orders targeting the effective location
        """
        if not isinstance(self.selected_obj, Fleet):
            return {'targets': [], 'location': (0, 0), 'display_mode': 'empty', 'default_target': None}
        
        # Get the location where the fleet will be when the transfer executes
        effective_x, effective_y = self.get_fleet_effective_location()
        
        targets = self._build_location_targets(
            effective_x,
            effective_y,
            include_stars=True,
            include_fleets=True,
            include_salvage=True,
            include_empty=True,
            include_future_fleets=True,
            fleet_player=self.player,
            exclude_fleet_id=self.selected_obj.id,
            include_order_types=['MOVE', 'INTERCEPT', 'PATROL'],
        )
        has_star = self.game.stars.filter(x=effective_x, y=effective_y).exists()
        has_salvage = self.game.salvages.filter(x=effective_x, y=effective_y).exists()
        if not has_star and not has_salvage:
            if not any(target.get('type') == 'space' for target in targets):
                empty_space_name = DetailBuilder.format_empty_space(effective_x, effective_y)
                targets.insert(0, {
                    'name': empty_space_name,
                    'short_id': '',
                    'type': 'space',
                })

        # Determine display mode and default target
        if not targets:
            return {
                'targets': [],
                'location': (effective_x, effective_y),
                'display_mode': 'empty',
                'default_target': None
            }
        if len(targets) == 1 and targets[0].get('type') == 'space':
            empty_space_name = DetailBuilder.format_empty_space(effective_x, effective_y)
            return {
                'targets': targets,
                'location': (effective_x, effective_y),
                'display_mode': 'empty',
                'default_target': empty_space_name
            }
        if len(targets) == 1:
            target = targets[0]
            display_name = f"{target['name']} ({target['type'].title()})"
            return {
                'targets': targets,
                'location': (effective_x, effective_y),
                'display_mode': 'single',
                'default_target': display_name
            }
        return {
            'targets': targets,
            'location': (effective_x, effective_y),
            'display_mode': 'multiple',
            'default_target': targets[0]
        }

    def get_colonise_targets(self):
        """Get available colonise targets at the fleet's effective location.

        Returns a dict with:
        - targets: list of available star targets
        - location: (x, y) coordinates
        - display_mode: 'single', 'multiple', or 'empty'
        - default_target: the target to select by default

        Only Stars are valid colonise targets (unlike Transfer which includes fleets).
        """
        if not isinstance(self.selected_obj, Fleet):
            return {'targets': [], 'location': (0, 0), 'display_mode': 'empty', 'default_target': None}

        # Get the location where the fleet will be when the colonise executes
        effective_x, effective_y = self.get_fleet_effective_location()

        targets = []

        # Add stars at the effective location (only stars, no fleets)
        stars_at_location = self.game.stars.filter(x=effective_x, y=effective_y).all()
        for star in stars_at_location:
            targets.append({
                'name': star.name,
                'short_id': star.short_id,
                'type': 'star'
            })

        # Determine display mode and default target
        if not targets:
            # No star at location - cannot colonise
            return {
                'targets': [],
                'location': (effective_x, effective_y),
                'display_mode': 'empty',
                'default_target': None
            }
        elif len(targets) == 1:
            # Single target
            target = targets[0]
            return {
                'targets': targets,
                'location': (effective_x, effective_y),
                'display_mode': 'single',
                'default_target': target
            }
        else:
            # Multiple stars (rare but possible)
            return {
                'targets': targets,
                'location': (effective_x, effective_y),
                'display_mode': 'multiple',
                'default_target': targets[0]
            }

    def get_bomb_targets(self):
        """Get available bombardment targets at the fleet's effective location."""
        if not isinstance(self.selected_obj, Fleet):
            return {'targets': [], 'location': (0, 0), 'display_mode': 'empty', 'default_target': None}
        if not self.selected_obj.has_bombs:
            return {'targets': [], 'location': (0, 0), 'display_mode': 'empty', 'default_target': None}

        effective_x, effective_y = self.get_fleet_effective_location()
        targets = []
        stars_at_location = self.game.stars.filter(x=effective_x, y=effective_y).all()
        for star in stars_at_location:
            targets.append({
                'name': star.name,
                'short_id': star.short_id,
                'type': 'star'
            })

        if not targets:
            return {
                'targets': [],
                'location': (effective_x, effective_y),
                'display_mode': 'empty',
                'default_target': None
            }
        if len(targets) == 1:
            return {
                'targets': targets,
                'location': (effective_x, effective_y),
                'display_mode': 'single',
                'default_target': targets[0]
            }
        return {
            'targets': targets,
            'location': (effective_x, effective_y),
            'display_mode': 'multiple',
            'default_target': targets[0]
        }

    def get_remotemine_targets(self):
        """Get available remote mining targets at the fleet's effective location."""
        if not isinstance(self.selected_obj, Fleet):
            return {'targets': [], 'location': (0, 0), 'display_mode': 'empty', 'default_target': None}
        if not self.selected_obj.has_miners:
            return {'targets': [], 'location': (0, 0), 'display_mode': 'empty', 'default_target': None}

        effective_x, effective_y = self.get_fleet_effective_location()
        targets = []
        stars_at_location = self.game.stars.filter(x=effective_x, y=effective_y).all()
        for star in stars_at_location:
            targets.append({
                'name': star.name,
                'short_id': star.short_id,
                'type': 'star'
            })

        if not targets:
            return {
                'targets': [],
                'location': (effective_x, effective_y),
                'display_mode': 'empty',
                'default_target': None
            }
        if len(targets) == 1:
            return {
                'targets': targets,
                'location': (effective_x, effective_y),
                'display_mode': 'single',
                'default_target': targets[0]
            }
        return {
            'targets': targets,
            'location': (effective_x, effective_y),
            'display_mode': 'multiple',
            'default_target': targets[0]
        }

    def get_merge_targets(self):
        """Get available merge targets at the fleet's effective location.

        Returns a dict with:
        - targets: list of available fleet targets (same player only)
        - location: (x, y) coordinates
        - display_mode: 'single', 'multiple', or 'empty'
        - default_target: the target to select by default

        Only fleets belonging to the same player are valid merge targets.
        Includes fleets currently at the location AND fleets with orders
        targeting the location.
        """
        if not isinstance(self.selected_obj, Fleet):
            return {
                'targets': [], 'location': (0, 0),
                'display_mode': 'empty', 'default_target': None
            }

        if not self.player or self.selected_obj.player != self.player:
            return {
                'targets': [], 'location': (0, 0),
                'display_mode': 'empty', 'default_target': None
            }

        # Get the location where the fleet will be when the merge executes
        effective_x, effective_y = self.get_fleet_effective_location()

        targets = self._build_location_targets(
            effective_x,
            effective_y,
            include_stars=True,
            include_fleets=True,
            include_salvage=False,
            include_empty=False,
            include_future_fleets=True,
            fleet_player=self.player,
            exclude_fleet_id=self.selected_obj.id,
            include_order_types=['MOVE', 'INTERCEPT', 'PATROL'],
        )
        # Merge targets should mirror transfer target logic but restricted to fleets.
        targets = [target for target in targets if target.get('type') == 'fleet']
        for target in targets:
            if target['type'] == 'fleet':
                fleet = self.game.fleets.filter(short_id=target['short_id']).first()
                if fleet:
                    target['ship_count'] = fleet.ship_count

        # Determine display mode and default target
        if not targets:
            return {
                'targets': [],
                'location': (effective_x, effective_y),
                'display_mode': 'empty',
                'default_target': None
            }
        elif len(targets) == 1:
            return {
                'targets': targets,
                'location': (effective_x, effective_y),
                'display_mode': 'single',
                'default_target': targets[0]
            }
        else:
            return {
                'targets': targets,
                'location': (effective_x, effective_y),
                'display_mode': 'multiple',
                'default_target': targets[0]
            }

    def get_patrol_targets(self):
        """Get available patrol targets at the fleet's effective location.

        Returns a dict with:
        - targets: list of available targets (stars and fleets, any player)
        - location: (x, y) coordinates
        - display_mode: 'single', 'multiple', or 'empty'
        - default_target: the target to select by default
        """
        if not isinstance(self.selected_obj, Fleet):
            return {'targets': [], 'location': (0, 0), 'display_mode': 'empty', 'default_target': None}

        effective_x, effective_y = self.get_fleet_effective_location()

        targets = self._build_location_targets(
            effective_x,
            effective_y,
            include_stars=True,
            include_fleets=True,
            include_salvage=False,
            include_empty=True,
            include_future_fleets=False,
            exclude_fleet_id=self.selected_obj.id,
        )

        if not targets:
            empty_space_name = self.format_empty_space(effective_x, effective_y)
            return {
                'targets': [],
                'location': (effective_x, effective_y),
                'display_mode': 'empty',
                'default_target': empty_space_name
            }
        if len(targets) == 1 and targets[0].get('type') == 'space':
            empty_space_name = self.format_empty_space(effective_x, effective_y)
            return {
                'targets': targets,
                'location': (effective_x, effective_y),
                'display_mode': 'empty',
                'default_target': empty_space_name
            }
        if len(targets) == 1:
            target = targets[0]
            display_name = f"{target['name']} ({target['type'].title()})"
            return {
                'targets': targets,
                'location': (effective_x, effective_y),
                'display_mode': 'single',
                'default_target': display_name
            }
        return {
            'targets': targets,
            'location': (effective_x, effective_y),
            'display_mode': 'multiple',
            'default_target': targets[0]
        }
