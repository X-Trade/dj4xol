from django.db import models
from dj4xol.models import Fleet, Star, Salvage, Anomaly, Report, PlayerStarMarker
from dj4xol.scanners import (
    fleet_is_cloaked,
    get_scanner_sources_for_player,
    fleet_visible_to_player,
    position_in_scanner_range,
)
from dj4xol.turn import (
    KT_PER_MINE,
    WORMHOLE_WARPFACTOR,
    apply_population_change,
    format_basic_hidden_salvage_name,
    format_basic_unknown_fleet_name,
)
from dj4xol.fleet_thumbnails import get_blurred_fleet_thumbnail
from dj4xol.star_thumbnails import get_blurred_star_thumbnail
from dj4xol.anomaly_thumbnails import get_blurred_anomaly_thumbnail
from dj4xol.mineral_rules import (
    ALL_RESOURCE_KEYS,
    BASE_MINERAL_KEYS,
    SECRET_RESOURCE_KEYS,
    known_resource_keys,
)
from dj4xol.secret_resources import get_secret_resource_label
from dj4xol.salvage_thumbnails import (
    get_blurred_salvage_thumbnail,
    get_salvage_thumbnail,
)
from dj4xol.hazard_rules import danger_level_display, object_danger_level
from dj4xol.diplomacy import build_stance_map, player_can_refuel_fleet
from dj4xol.research import (
    get_player_administration_profile,
    get_player_colony_defense_level,
    get_player_colony_scanner_ranges,
    get_player_production_costs,
    get_player_terraforming_profile,
    format_terraform_order_label,
    get_player_available_production_orders,
)
from dj4xol.micromanager_rules import ADMINISTRATION_ONE_OFF_ORDER_TYPES
from dj4xol.colony_rules import (
    calculate_growth_factor,
    calculate_habitability_factor,
    effective_capacity,
    habitability_value_for_environment,
    limit_population_growth_by_surface_resources,
    player_ignores_environment,
    population_growth_uses_surface_resources,
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

    RESOURCE_LABELS = {
        'ironium': 'Ironium',
        'boranium': 'Boranium',
        'germanium': 'Germanium',
    }

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
        if speed == 14:
            # Wormhole jump mode is always resolved within one year.
            return 1
        return max(1, int(ceil(distance / float(speed))))

    def __init__(self, game, x=None, y=None, selected=None, player=None,
                 viewer_account=None, detail_mode=None):
        self.game = game
        self.player = player
        self.viewer_account = viewer_account
        self.detail_mode = detail_mode
        self.spectator_mode = detail_mode in ('spectator_basic', 'spectator_admin')
        self.admin_view = detail_mode == 'spectator_admin'
        self._scanner_sources = (
            get_scanner_sources_for_player(game, player)
            if player and not self.spectator_mode else []
        )
        self._reported_salvage_ids = set()
        if self.spectator_mode or self.admin_view:
            self._reported_salvage_ids = set(
                self.game.salvages.values_list('id', flat=True)
            )
        elif self.player:
            self._reported_salvage_ids = set(
                Report.objects.filter(
                    game=self.game,
                    player=self.player,
                    target_type='salvage',
                ).values_list('target_id', flat=True)
            )
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
            if self.admin_view:
                return self._build_admin_detail()
            if self.spectator_mode:
                return self._build_spectator_detail()
            can_view, report_year = self.can_view_object(self.selected_obj)

            if not can_view:
                # Return unexplored placeholder
                marker_star = self._get_marker_star() if isinstance(self.selected_obj, Star) else None
                return {
                    'name': self.get_object_name(),
                    'selected_id': self.selected_obj.short_id,
                    'objects_here': self.get_objects_here(),
                    'unexplored': True,
                    'owner_known': False,
                    'x': self.selected_obj.x,
                    'y': self.selected_obj.y,
                    'is_star': isinstance(self.selected_obj, Star),
                    'is_fleet': isinstance(self.selected_obj, Fleet),
                    'is_salvage': isinstance(self.selected_obj, Salvage),
                    'is_anomaly': isinstance(self.selected_obj, Anomaly),
                    'position_status': 'unknown' if isinstance(self.selected_obj, Fleet) else 'current',
                    'suppress_locate': isinstance(self.selected_obj, Fleet),
                    'thumbnail_blurred': False,
                    'can_set_marker': bool(self.player and isinstance(self.selected_obj, Star)),
                    'star_marker_type': self._get_star_marker_type() if isinstance(self.selected_obj, Star) else '',
                    'star_marker_color': self._get_star_marker_color() if isinstance(self.selected_obj, Star) else PlayerStarMarker.COLOR_BLUE,
                    'marker_star_short_id': marker_star.short_id if marker_star else None,
                    'star_short_id': self.selected_obj.short_id if isinstance(self.selected_obj, Star) else None,
                }

            if report_year is not None:
                # Load from cached report
                return self._build_detail_from_report(report_year)

            # Current data (owned or fleet present)
            is_selected_fleet = isinstance(self.selected_obj, Fleet)
            can_show_fleet_levels = (
                self._can_show_fleet_level_data(self.selected_obj)
                if is_selected_fleet else False
            )
            detail = {'name': self.get_object_name(),
                     'selected_id': self.selected_obj.short_id,
                     'objects_here': self.get_objects_here(),
                     'player': self.get_object_player(),
                     'is_owned': self.selected_obj.player == self.player if self.player else False,
                     'owner_known': bool(self.get_object_player()),
                     'show_composition': True,
                     'is_survivable': self.get_survivability(),
                     'population': self.get_population(),
                     'population_change': self.get_population_change(),
                     'capacity': self.get_effective_capacity(),
                     'environmentals': self.build_environmental_detail(),
                     'resources': self.build_resource_detail(),
                     'infrastructure': self.build_infrastructure_detail(),
                     'infrastructure_has_any': (
                         self._star_has_leftover_infrastructure(self.selected_obj)
                         if isinstance(self.selected_obj, Star) else False
                     ),
                     'is_star': isinstance(self.selected_obj, Star),
                     'is_fleet': isinstance(self.selected_obj, Fleet),
                     'is_salvage': isinstance(self.selected_obj, Salvage),
                     'is_anomaly': isinstance(self.selected_obj, Anomaly),
                     'fleet_thumbnail': (
                         self.selected_obj.effective_thumbnail_path
                         if isinstance(self.selected_obj, Fleet) else None
                     ),
                     'star_thumbnail': (
                         self.selected_obj.effective_thumbnail_path
                         if isinstance(self.selected_obj, Star) else None
                     ),
                     'anomaly_thumbnail': (
                         self.selected_obj.effective_thumbnail_path
                         if isinstance(self.selected_obj, Anomaly) else None
                     ),
                     'salvage_thumbnail': (
                         get_salvage_thumbnail(self.selected_obj)
                         if isinstance(self.selected_obj, Salvage) else None
                     ),
                     'can_set_marker': bool(self.player and isinstance(self.selected_obj, Star)),
                     'star_marker_type': self._get_star_marker_type() if isinstance(self.selected_obj, Star) else '',
                     'star_marker_color': self._get_star_marker_color() if isinstance(self.selected_obj, Star) else PlayerStarMarker.COLOR_BLUE,
                     'marker_star_short_id': self._get_marker_star().short_id if isinstance(self.selected_obj, Star) and self._get_marker_star() else None,
                     'star_short_id': self.selected_obj.short_id if isinstance(self.selected_obj, Star) else None,
                     'fleet_short_id': self.selected_obj.short_id if isinstance(self.selected_obj, Fleet) else None,
                     'salvage_short_id': self.selected_obj.short_id if isinstance(self.selected_obj, Salvage) else None,
                     'salvage_type': self.selected_obj.salvage_type if isinstance(self.selected_obj, Salvage) else None,
                     'salvage_type_display': (
                         self.selected_obj.get_salvage_type_display()
                         if isinstance(self.selected_obj, Salvage) else None
                     ),
                     'danger_level': (
                         object_danger_level(self.selected_obj)
                         if isinstance(self.selected_obj, (Salvage, Anomaly)) else None
                     ),
                     'danger_level_display': (
                         danger_level_display(object_danger_level(self.selected_obj))
                         if isinstance(self.selected_obj, (Salvage, Anomaly)) else None
                     ),
                     'anomaly_short_id': self.selected_obj.short_id if isinstance(self.selected_obj, Anomaly) else None,
                     'anomaly_type': self.selected_obj.anomaly_type if isinstance(self.selected_obj, Anomaly) else None,
                     'stability': self.selected_obj.stability if isinstance(self.selected_obj, Anomaly) else None,
                     'heading': (
                         self.selected_obj.heading
                         if isinstance(self.selected_obj, (Anomaly, Fleet)) else None
                     ),
                     'travel_warp': (
                         self._fleet_travel_warp(self.selected_obj)
                         if isinstance(self.selected_obj, Fleet) else None
                     ),
                     'warp_advantage': (
                         self._fleet_warp_advantage(self.selected_obj)
                         if isinstance(self.selected_obj, Fleet) else None
                     ),
                     'is_cloaked': (
                         fleet_is_cloaked(self.selected_obj)
                         if isinstance(self.selected_obj, Fleet) else False
                     ),
                     'position_status': 'current',
                     'last_known_position': None,
                     'last_known_report_year': None,
                     'suppress_locate': False,
                     'fleet_motion_summary': None,
                     'salvage_inventory': self.build_salvage_inventory(),
                     'production_orders': self.get_production_orders(),
                     'production_order_choices': self.get_available_production_orders(),
                     'fleet_orders': self.get_fleet_orders(),
                     'fleet_cargo': self.get_fleet_cargo(),
                     'fleet_capabilities': self.get_fleet_capabilities(
                         include_scanners=can_show_fleet_levels,
                         allow_foreign_levels=can_show_fleet_levels,
                     ),
                     'fleet_inventory': self.build_fleet_inventory(),
                     'transfer_targets': self.get_transfer_targets(),
                     'refuel_targets': self.get_refuel_targets(),
                     'transfer_recipients': self.get_transfer_recipients(),
                     'colonise_targets': self.get_colonise_targets(),
                     'bomb_targets': self.get_bomb_targets(),
                     'remotemine_targets': self.get_remotemine_targets(),
                     'remotemine_focus_options': self.get_remotemine_focus_options(),
                     'merge_targets': self.get_merge_targets(),
                     'patrol_targets': self.get_patrol_targets(),
                     'effective_location': self.get_fleet_effective_location() if isinstance(self.selected_obj, Fleet) else None,
                     'secret_resource_labels': {key: self._resource_label(key) for key in SECRET_RESOURCE_KEYS},
                     'x': self.selected_obj.x,
                     'y': self.selected_obj.y,
                     'report_tier': (
                         None if (not is_selected_fleet or can_show_fleet_levels)
                         else 'basic'
                     ),
                     'report_year': None,
                     'is_last_known': False,
                     'is_current': True,
                     'thumbnail_blurred': False,
                     }
            self._apply_fleet_motion_summary(detail)
            if detail['effective_location']:
                effective_x, effective_y = detail['effective_location']
                detail['effective_location_name'] = self.format_empty_space(effective_x, effective_y)
        else:
            detail = None
        return detail

    def _build_detail_shell(self):
        obj = self.selected_obj
        return {
            'name': self.get_object_name(),
            'selected_id': obj.short_id,
            'objects_here': self.get_objects_here(),
            'is_star': isinstance(obj, Star),
            'is_fleet': isinstance(obj, Fleet),
            'is_salvage': isinstance(obj, Salvage),
            'is_anomaly': isinstance(obj, Anomaly),
            'fleet_thumbnail': (
                obj.effective_thumbnail_path if isinstance(obj, Fleet) else None
            ),
            'star_thumbnail': (
                obj.effective_thumbnail_path if isinstance(obj, Star) else None
            ),
            'anomaly_thumbnail': (
                obj.effective_thumbnail_path if isinstance(obj, Anomaly) else None
            ),
            'salvage_thumbnail': (
                get_salvage_thumbnail(obj) if isinstance(obj, Salvage) else None
            ),
            'star_short_id': obj.short_id if isinstance(obj, Star) else None,
            'fleet_short_id': obj.short_id if isinstance(obj, Fleet) else None,
            'salvage_short_id': obj.short_id if isinstance(obj, Salvage) else None,
            'salvage_type': obj.salvage_type if isinstance(obj, Salvage) else None,
            'salvage_type_display': (
                obj.get_salvage_type_display() if isinstance(obj, Salvage) else None
            ),
            'danger_level': object_danger_level(obj) if isinstance(obj, (Salvage, Anomaly)) else None,
            'danger_level_display': (
                danger_level_display(object_danger_level(obj))
                if isinstance(obj, (Salvage, Anomaly)) else None
            ),
            'anomaly_short_id': obj.short_id if isinstance(obj, Anomaly) else None,
            'anomaly_type': obj.anomaly_type if isinstance(obj, Anomaly) else None,
            'stability': obj.stability if isinstance(obj, Anomaly) else None,
            'heading': (
                obj.heading if isinstance(obj, (Anomaly, Fleet)) else None
            ),
            'travel_warp': (
                self._fleet_travel_warp(obj) if isinstance(obj, Fleet) else None
            ),
            'warp_advantage': (
                self._fleet_warp_advantage(obj) if isinstance(obj, Fleet) else None
            ),
            'is_cloaked': (
                fleet_is_cloaked(obj) if isinstance(obj, Fleet) else False
            ),
            'position_status': 'current',
            'last_known_position': None,
            'last_known_report_year': None,
            'is_last_known': False,
            'suppress_locate': False,
            'fleet_motion_summary': None,
            'secret_resource_labels': {key: self._resource_label(key) for key in SECRET_RESOURCE_KEYS},
            'x': obj.x,
            'y': obj.y,
            'thumbnail_blurred': False,
            'can_set_marker': False,
            'star_marker_type': '',
            'star_marker_color': PlayerStarMarker.COLOR_BLUE,
            'marker_star_short_id': None,
            'infrastructure_has_any': False,
        }

    def _build_spectator_detail(self):
        detail = self._build_detail_shell()
        detail.update({
            'player': self.get_object_player(),
            'is_owned': False,
            'owner_known': True,
            'show_composition': False,
            'report_tier': 'basic',
            'is_survivable': None,
            'population': self.get_population(),
            'population_change': None,
            'capacity': None,
            'environmentals': self.build_environmental_detail(),
            'resources': self.build_resource_detail(),
            'infrastructure': None,
            'salvage_inventory': None,
            'fleet_inventory': self.build_fleet_inventory(allow_foreign=True),
            'fleet_cargo': self._build_spectator_fleet_capacity(),
            'fleet_capabilities': None,
            'report_year': None,
            'is_current': True,
        })
        if detail.get('is_anomaly'):
            detail['stability'] = None
        self._apply_fleet_motion_summary(detail)
        return detail

    def _build_admin_detail(self):
        detail = self._build_detail_shell()
        detail.update({
            'player': self.get_object_player(),
            'is_owned': False,
            'owner_known': True,
            'show_composition': True,
            'report_tier': None,
            'is_survivable': None,
            'population': self.get_population(),
            'population_change': None,
            'capacity': None,
            'environmentals': self.build_environmental_detail(),
            'resources': self.build_resource_detail(),
            'infrastructure': self.build_infrastructure_detail(),
            'salvage_inventory': self.build_salvage_inventory(),
            'fleet_inventory': self.build_fleet_inventory(allow_foreign=True),
            'fleet_cargo': self.get_fleet_cargo(include_cargo=True),
            'fleet_capabilities': self.get_fleet_capabilities(
                include_scanners=True,
                allow_foreign_levels=True,
            ),
            'report_year': None,
            'is_current': True,
        })
        self._apply_fleet_motion_summary(detail)
        return detail

    def _build_spectator_fleet_capacity(self):
        if not self.selected_obj or not isinstance(self.selected_obj, Fleet):
            return None
        return {
            'capacity': self.selected_obj.cargo_capacity,
        }

    def _build_detail_from_report(self, report_year):
        """Build detail dict from a cached report."""
        target_type = self._get_target_type(self.selected_obj)
        report = Report.objects.get(
            player=self.player,
            target_type=target_type,
            target_id=self.selected_obj.id
        )
        data = report.get_report_data()
        report_tier = data.get('report_tier')
        report_owner_name = self._format_report_owner_display(data.get('player_name'))
        if target_type == 'fleet' and report_tier in ('ownership', 'advanced', 'encounter'):
            report_owner_name = report_owner_name or 'Abandoned'

        # Base detail fields
        detail = {
            'name': self._reported_object_name(self.selected_obj, target_type, data),
            'selected_id': self.selected_obj.short_id,
            'objects_here': self.get_objects_here(),
            'x': data.get('x', self.selected_obj.x),
            'y': data.get('y', self.selected_obj.y),
            'is_star': target_type == 'star',
            'is_fleet': target_type == 'fleet',
            'is_salvage': target_type == 'salvage',
            'is_anomaly': target_type == 'anomaly',
            'fleet_thumbnail': (
                self.selected_obj.effective_thumbnail_path if target_type == 'fleet' else None
            ),
            'star_thumbnail': (
                self.selected_obj.effective_thumbnail_path if target_type == 'star' else None
            ),
            'anomaly_thumbnail': (
                self.selected_obj.effective_thumbnail_path if target_type == 'anomaly' else None
            ),
            'salvage_thumbnail': (
                get_salvage_thumbnail(self.selected_obj) if target_type == 'salvage' else None
            ),
            'report_year': report_year,
            'report_age': self.game.year - report_year,
            'is_current': False,
            'is_owned': False,
            'report_tier': report_tier,
            'owner_known': bool(report_owner_name),
            'show_composition': True,
            'thumbnail_blurred': report_tier == 'basic',
            'heading': None,
            'travel_warp': None,
            'warp_advantage': None,
            'position_status': 'report',
            'last_known_position': None,
            'last_known_report_year': None,
            'is_last_known': False,
            'suppress_locate': False,
            'infrastructure_has_any': False,
        }
        self._apply_report_thumbnail_paths(detail, report_tier)

        # Add player name from cached data
        if report_owner_name:
            detail['player'] = report_owner_name

        # Type-specific fields from cached report
        if target_type == 'star':
            detail['star_short_id'] = self.selected_obj.short_id
            detail['can_set_marker'] = bool(self.player)
            detail['star_marker_type'] = self._get_star_marker_type()
            detail['star_marker_color'] = self._get_star_marker_color()
            marker_star = self._get_marker_star()
            detail['marker_star_short_id'] = marker_star.short_id if marker_star else None
            detail['population'] = data.get('colonists')
            detail['capacity'] = data.get('capacity')
            detail['is_survivable'] = data.get('is_survivable')
            if all(k in data for k in [
                'ironium_yield', 'boranium_yield', 'germanium_yield',
                'ironium_inventory', 'boranium_inventory', 'germanium_inventory',
            ]):
                resources = {}
                for key in ALL_RESOURCE_KEYS:
                    yield_val = int(data.get(f'{key}_yield', 0) or 0)
                    surface_val = int(data.get(f'{key}_inventory', 0) or 0)
                    if key in SECRET_RESOURCE_KEYS and yield_val <= 0 and surface_val <= 0:
                        continue
                    resources[key] = {
                        'label': self._resource_label(key),
                        'yield': yield_val,
                        'surface': surface_val,
                        'mining_rate': 0,
                    }
                if resources:
                    detail['resources'] = resources
            elif report_tier == 'basic':
                detail['resources_unknown'] = True
            # Build environmental detail from cached data
            if all(k in data for k in ['gravity', 'temperature', 'radiation']):
                detail['environmentals'] = self._build_env_from_report(data)
                if detail['capacity'] is None:
                    detail['capacity'] = self._capacity_from_report(data)
                if detail['is_survivable'] is None:
                    detail['is_survivable'] = self._is_survivable_from_report(data)
            if all(k in data for k in [
                'mines', 'factories', 'factories_bp', 'labs', 'labs_rp',
                'defenses', 'shipyards',
            ]):
                detail['infrastructure_has_any'] = any(
                    int(data.get(field, 0) or 0) > 0
                    for field in ('mines', 'factories', 'labs', 'defenses', 'shipyards')
                )
                scanner_display = None
                if 'basic_scanner_range' in data or 'advanced_scanner_range' in data:
                    scanner_display = self._format_scanner_range(
                        data.get('basic_scanner_range', 0),
                        data.get('advanced_scanner_range', 0),
                    )
                detail['infrastructure'] = {
                    'Mines': data.get('mines'),
                    'Factories': data.get('factories'),
                    'FactoriesBP': data.get('factories_bp'),
                    'Labs': data.get('labs'),
                    'LabsRP': data.get('labs_rp'),
                    'Scanners': scanner_display,
                    'Defenses': data.get('defenses'),
                    'DefensesTooltip': data.get('defenses_tooltip'),
                    'Shipyards': data.get('shipyards'),
                    'Jobs': {
                        'count': data.get('jobs_count', 0),
                        'employment': data.get('jobs_employment', 0.0),
                    },
                }
            if (
                not detail.get('player') and
                any(
                    int(data.get(field, 0) or 0) > 0
                    for field in ('mines', 'factories', 'labs', 'defenses', 'shipyards')
                )
            ):
                detail['player'] = 'Abandoned'
                detail['owner_known'] = True
        elif target_type == 'fleet':
            detail['fleet_short_id'] = self.selected_obj.short_id
            stale_fleet_report = not self._is_fleet_currently_visible(self.selected_obj)
            detail['position_status'] = 'last_known' if stale_fleet_report else 'report'
            detail['is_cloaked'] = bool(data.get('is_cloaked'))
            if stale_fleet_report and detail.get('x') is not None and detail.get('y') is not None:
                detail['last_known_position'] = self.format_empty_space(
                    detail.get('x'),
                    detail.get('y'),
                )
                detail['last_known_report_year'] = report_year
                detail['is_last_known'] = True
            if data.get('heading') is not None:
                detail['heading'] = data.get('heading')
            if data.get('warp_advantage') is not None:
                detail['warp_advantage'] = self._fleet_warp_advantage_from_data(
                    data.get('warp_advantage')
                )
            if data.get('travel_warp') is not None:
                detail['travel_warp'] = self._effective_travel_warp(
                    data.get('travel_warp'),
                    detail.get('warp_advantage'),
                )
            if not stale_fleet_report:
                # Fleet is currently visible: always show live positional/motion state.
                detail['x'] = self.selected_obj.x
                detail['y'] = self.selected_obj.y
                detail['heading'] = self.selected_obj.heading
                detail['travel_warp'] = self._fleet_travel_warp(self.selected_obj)
                detail['warp_advantage'] = self._fleet_warp_advantage(self.selected_obj)
                detail['is_cloaked'] = fleet_is_cloaked(self.selected_obj)
            if self._should_show_live_fleet_identity(self.selected_obj, data):
                detail['name'] = self.selected_obj.name
                detail['player'] = self.selected_obj.owner_display_name
                detail['owner_known'] = True
            if 'ship_count' in data:
                detail['fleet_cargo'] = {
                    'ship_count': data.get('ship_count'),
                    'integrity': data.get('integrity'),
                    'offense_modifier': data.get('offense_modifier'),
                    'defense_modifier': data.get('defense_modifier'),
                    'has_bombs': data.get('has_bombs'),
                    'has_miners': data.get('has_miners'),
                    'has_fuel_factory': data.get('has_fuel_factory'),
                    'fuel_factory_mg_per_year': data.get(
                        'fuel_factory_mg_per_year', 0.0
                    ),
                    'fuel_factory_max_warp': data.get(
                        'fuel_factory_max_warp', -1
                    ),
                    'has_wormhole_drive': data.get('has_wormhole_drive'),
                }
                if data.get('report_tier') == 'encounter':
                    detail['fleet_capabilities'] = self._build_fleet_capabilities(
                        data.get('max_safe_warp'),
                        data.get('warp_advantage'),
                        data.get('max_cloaked_warp', -1),
                        bool(data.get('advanced_cloak')),
                        data.get('has_bombs'),
                        data.get('has_miners'),
                        data.get('fuel_factory_mg_per_year', 0.0),
                        bool(data.get('has_wormhole_drive')),
                        data.get('basic_scanner_range', 0),
                        data.get('advanced_scanner_range', 0),
                        include_scanners=True,
                    )
            if 'cargo_capacity' in data and data.get('cargo_capacity') is not None:
                detail['fleet_inventory'] = self._build_fleet_inventory_from_report(data)
        elif target_type == 'salvage':
            detail['salvage_short_id'] = self.selected_obj.short_id
            if self._report_hides_ancient_debris_type(data):
                detail['salvage_type'] = None
                detail['salvage_type_display'] = '???'
            else:
                detail['salvage_type'] = data.get('salvage_type')
                detail['salvage_type_display'] = self._salvage_type_display_from_code(
                    data.get('salvage_type')
                )
            detail['danger_level'] = None
            detail['danger_level_display'] = None
            if str(data.get('report_tier') or '').lower() in ('advanced', 'encounter'):
                detail['danger_level'] = data.get('danger_level') or object_danger_level(self.selected_obj)
                detail['danger_level_display'] = (
                    danger_level_display(
                        detail['danger_level'],
                        detail.get('stability') if detail.get('is_anomaly') else None,
                    )
                    if detail.get('danger_level') else None
                )
            if 'total_minerals' in data:
                items = []
                has_inventory_breakdown = False
                for key in ALL_RESOURCE_KEYS:
                    amount_key = f'{key}_inventory'
                    if amount_key in data:
                        has_inventory_breakdown = True
                    amount = int(data.get(amount_key, 0) or 0)
                    if amount <= 0:
                        continue
                    items.append({
                        'label': self._resource_label(key),
                        'amount': amount,
                    })
                detail['salvage_inventory'] = {
                    'items': items,
                    'total': data['total_minerals'],
                    'composition_unknown': not has_inventory_breakdown,
                }
        elif target_type == 'anomaly':
            detail['anomaly_short_id'] = self.selected_obj.short_id
            detail['anomaly_type'] = data.get('anomaly_type')
            detail['description'] = data.get('description')
            detail['stability'] = data.get('stability')
            detail['heading'] = data.get('heading')
            detail['danger_level'] = None
            detail['danger_level_display'] = None
            if str(data.get('report_tier') or '').lower() in ('advanced', 'encounter'):
                detail['danger_level'] = data.get('danger_level') or object_danger_level(self.selected_obj)
                detail['danger_level_display'] = (
                    danger_level_display(detail['danger_level'])
                    if detail.get('danger_level') else None
                )

        self._apply_fleet_motion_summary(detail)
        return detail

    def _get_star_marker_type(self):
        marker = self._get_star_marker()
        if marker is None:
            return ''
        return getattr(marker, 'marker_type', '') or ''

    def _get_star_marker_color(self):
        marker = self._get_star_marker()
        if marker is None:
            return PlayerStarMarker.COLOR_BLUE
        color = str(getattr(marker, 'marker_color', '') or '').upper()
        if color == PlayerStarMarker.COLOR_WHITE:
            return PlayerStarMarker.COLOR_BLUE
        if color in PlayerStarMarker.COLOR_VALUES:
            return color
        return PlayerStarMarker.COLOR_BLUE

    def _get_star_marker(self):
        marker_star = self._get_marker_star()
        if not self.player or marker_star is None:
            return None
        markers = list(
            PlayerStarMarker.objects.filter(
                player=self.player,
                star__game=self.game,
                star__x=marker_star.x,
                star__y=marker_star.y,
            ).select_related('star')
        )
        if not markers:
            return None
        for marker in markers:
            if getattr(marker, 'star_id', None) == getattr(marker_star, 'id', None):
                return marker
        return markers[0]

    def _get_marker_star(self):
        if not self.selected_obj or not isinstance(self.selected_obj, Star):
            return None
        stars = list(
            Star.objects.filter(
                game=self.game,
                x=self.selected_obj.x,
                y=self.selected_obj.y,
            )
        )
        if not stars:
            return self.selected_obj
        return sorted(
            stars,
            key=self._marker_star_sort_key,
        )[0]

    def _marker_star_sort_key(self, star):
        owner = getattr(star, 'player', None)
        owner_priority = 0 if self.player and owner == self.player else (1 if owner else 2)
        homeworld_priority = -1 if (
            self.player and self.player.homeworld_id == getattr(star, 'id', None)
        ) else 0
        return (
            owner_priority,
            homeworld_priority,
            str(getattr(star, 'short_id', '') or ''),
            int(getattr(star, 'id', 0) or 0),
        )

    def _apply_fleet_motion_summary(self, detail):
        """Attach a user-facing fleet movement summary line to detail payload."""
        if not detail or not detail.get('is_fleet'):
            return
        if (
            detail.get('position_status') == 'last_known' and
            detail.get('last_known_position')
        ):
            detail['fleet_motion_summary'] = (
                'Last known position: %s' % detail.get('last_known_position')
            )
            return
        detail['fleet_motion_summary'] = self._build_fleet_motion_summary(
            detail.get('travel_warp'),
            detail.get('heading'),
            detail.get('x'),
            detail.get('y'),
            detail.get('is_cloaked'),
        )

    def _build_fleet_motion_summary(self, travel_warp, heading, x, y, is_cloaked=False):
        """Return readable motion status for fleet detail header."""
        speed = None
        if travel_warp is not None:
            try:
                speed = float(travel_warp)
            except (TypeError, ValueError):
                speed = None

        if speed is None:
            summary = 'Travelling at Warp Unknown'
            if heading is None:
                return self._append_cloaked_status(summary, is_cloaked)
            try:
                return self._append_cloaked_status(
                    '%s | Heading %.1f°' % (summary, float(heading)),
                    is_cloaked,
                )
            except (TypeError, ValueError):
                return self._append_cloaked_status(summary, is_cloaked)

        if speed <= 0.0:
            if self._has_star_at_position(x, y):
                return self._append_cloaked_status('In orbit', is_cloaked)
            return self._append_cloaked_status('Stopped', is_cloaked)

        summary = 'Travelling at Warp %s' % self._format_warp_value(speed)
        if heading is None:
            return self._append_cloaked_status(summary, is_cloaked)
        try:
            return self._append_cloaked_status(
                '%s | Heading %.1f°' % (summary, float(heading)),
                is_cloaked,
            )
        except (TypeError, ValueError):
            return self._append_cloaked_status(summary, is_cloaked)

    def _append_cloaked_status(self, summary, is_cloaked):
        if is_cloaked:
            return '%s | cloaked' % summary
        return summary

    def _has_star_at_position(self, x, y):
        """Return True if any star exists at the given coordinates."""
        if x is None or y is None:
            return False
        try:
            check_x = int(x)
            check_y = int(y)
        except (TypeError, ValueError):
            return False
        return Star.objects.filter(game=self.game, x=check_x, y=check_y).exists()

    def _apply_report_thumbnail_paths(self, detail, report_tier):
        if report_tier != 'basic':
            return detail
        if detail.get('fleet_thumbnail'):
            detail['fleet_thumbnail'] = get_blurred_fleet_thumbnail(
                detail['fleet_thumbnail']
            )
        if detail.get('star_thumbnail'):
            detail['star_thumbnail'] = get_blurred_star_thumbnail(
                detail['star_thumbnail']
            )
        if detail.get('anomaly_thumbnail'):
            detail['anomaly_thumbnail'] = get_blurred_anomaly_thumbnail(
                detail['anomaly_thumbnail']
            )
        if detail.get('salvage_thumbnail'):
            detail['salvage_thumbnail'] = get_blurred_salvage_thumbnail(
                self.selected_obj
            )
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

    def _build_fleet_inventory_from_report(self, data):
        """Build fleet cargo inventory data from report for display."""
        try:
            capacity = float(data.get('cargo_capacity') or 0)
        except (TypeError, ValueError):
            capacity = 0.0
        try:
            fuel_cap = float(data.get('max_fuel') or 0)
        except (TypeError, ValueError):
            fuel_cap = 0.0
        inventory = {
            'fuel': dict(self._build_cargo_data(data.get('fuel') or 0, fuel_cap, 'mg'), label='Fuel'),
            'ironium': dict(self._build_cargo_data(data.get('ironium_inventory') or 0, capacity, 'kt'), label='Ironium'),
            'boranium': dict(self._build_cargo_data(data.get('boranium_inventory') or 0, capacity, 'kt'), label='Boranium'),
            'germanium': dict(self._build_cargo_data(data.get('germanium_inventory') or 0, capacity, 'kt'), label='Germanium'),
            'colonists': dict(self._build_cargo_data(data.get('colonists') or 0, capacity, 'k'), label='Colonists'),
        }
        for key in SECRET_RESOURCE_KEYS:
            amount = int(data.get(f'{key}_inventory', 0) or 0)
            if amount <= 0:
                continue
            inventory[key] = dict(
                self._build_cargo_data(amount, capacity, 'kt'),
                label=self._resource_label(key),
            )
        return inventory

    def get_objects_here(self):
        """Return list of dicts with name, short_id, and type for all objects at cursor."""
        result = []
        for obj in self.at_cursor:
            if isinstance(obj, Salvage):
                name = self._salvage_display_name(obj)
            elif self.player:
                can_view, report_year = self.can_view_object(obj)
                if can_view and report_year is not None:
                    target_type = self._get_target_type(obj)
                    report = Report.objects.filter(
                        player=self.player,
                        target_type=target_type,
                        target_id=obj.id
                    ).first()
                    if report:
                        data = report.get_report_data()
                        name = self._reported_object_name(obj, target_type, data)
                    else:
                        name = obj.name or f"{obj.__class__.__name__} {obj.id}"
                else:
                    name = obj.name or f"{obj.__class__.__name__} {obj.id}"
            else:
                name = obj.name or f"{obj.__class__.__name__} {obj.id}"
            if isinstance(obj, Star):
                obj_type = 'star'
            elif isinstance(obj, Fleet):
                obj_type = 'fleet'
            elif isinstance(obj, Salvage):
                obj_type = 'salvage'
            elif isinstance(obj, Anomaly):
                obj_type = 'anomaly'
            else:
                obj_type = 'unknown'
            result.append(self._decorate_target({
                'name': name,
                'short_id': obj.short_id,
                'type': obj_type,
                'is_homeworld': bool(
                    self.player and isinstance(obj, Star) and
                    obj.id == self.player.homeworld_id
                ),
                'is_owned': bool(
                    self.player and hasattr(obj, 'player_id') and
                    obj.player_id == self.player.id
                ),
                'is_future': False,
            }))
        return self._sort_targets(result)

    def _salvage_display_name(self, salvage):
        if salvage is None:
            return ""
        if salvage.name is None or len(salvage.name) == 0:
            return f"{salvage.__class__.__name__} {salvage.id}"
        return salvage.name

    def _reported_object_name(self, obj, target_type, data):
        """Return the display name to use for a cached report."""
        report_tier = data.get('report_tier')
        if report_tier == 'basic':
            if target_type == 'fleet':
                if self._should_show_live_fleet_identity(obj, data):
                    return obj.name or f"{obj.__class__.__name__} {obj.id}"
                return format_basic_unknown_fleet_name(obj)
            if (
                target_type == 'salvage' and
                not getattr(self.game, 'no_scanners', False)
            ):
                if data.get('report_tier') == 'basic':
                    return format_basic_hidden_salvage_name(obj)
        return data.get('name') or obj.name or f"{obj.__class__.__name__} {obj.id}"

    def _get_cached_report_data(self, obj, target_type):
        """Return cached report data for object when available."""
        if not self.player:
            return None
        report = Report.objects.filter(
            player=self.player,
            target_type=target_type,
            target_id=obj.id,
        ).first()
        if not report:
            return None
        try:
            return report.get_report_data()
        except Exception:
            return None

    def _report_hides_ancient_debris_type(self, data):
        if getattr(self.game, 'no_scanners', False):
            return False
        return (
            data.get('report_tier') == 'basic' and
            isinstance(self.selected_obj, Salvage) and
            getattr(self.selected_obj, 'salvage_type', None) == Salvage.TYPE_ANCIENT_DEBRIS
        )

    def _salvage_type_display_from_code(self, salvage_type):
        if not salvage_type:
            return None
        if (
            isinstance(self.selected_obj, Salvage) and
            getattr(self.selected_obj, 'salvage_type', None) == salvage_type
        ):
            return self.selected_obj.get_salvage_type_display()
        return dict(Salvage.SALVAGE_TYPE_CHOICES).get(
            salvage_type,
            str(salvage_type).replace('_', ' ').title(),
        )

    def _fleet_report_coordinates(self, fleet):
        """Return cached report (x, y) for a fleet when available."""
        if not fleet or not isinstance(fleet, Fleet):
            return (None, None)
        data = self._get_cached_report_data(fleet, 'fleet') or {}
        x = data.get('x')
        y = data.get('y')
        if x is None or y is None:
            return (None, None)
        try:
            return (int(x), int(y))
        except (TypeError, ValueError):
            return (None, None)

    def _is_fleet_currently_visible(self, fleet):
        """Return True when fleet is currently visible to this viewer."""
        if not fleet or not isinstance(fleet, Fleet):
            return False
        if self.spectator_mode or self.admin_view:
            return True
        if not self.player:
            return False
        if fleet.player_id == self.player.id:
            return True
        return fleet_visible_to_player(
            fleet,
            self.player,
            sources=self._scanner_sources,
        )

    def _player_has_persistent_contact_with_owner(self, owner):
        """Return True when viewer has already resolved this player's identity."""
        if not self.player or not owner:
            return False
        if owner.id == self.player.id:
            return True

        from dj4xol.models import PlayerDiplomaticStance

        if PlayerDiplomaticStance.objects.filter(
            player=self.player,
            target_player=owner,
        ).exists():
            return True

        for report in Report.objects.filter(
            player=self.player,
            target_type__in=['fleet', 'star'],
        ).order_by('id'):
            try:
                data = report.get_report_data()
            except Exception:
                continue
            if data.get('player_name') == owner.name:
                return True
        return False

    def _should_show_live_fleet_identity(self, fleet, report_data=None):
        """Return True when a no-scanners fleet should keep resolved identity."""
        if not fleet or not isinstance(fleet, Fleet):
            return False
        if self.spectator_mode or self.admin_view:
            return True
        if not self.player:
            return False
        if fleet.player_id == self.player.id:
            return True
        if not getattr(self.game, 'no_scanners', False):
            return False
        if report_data and report_data.get('player_name'):
            return True
        return self._player_has_persistent_contact_with_owner(
            getattr(fleet, 'player', None)
        )

    def _fleet_travel_warp(self, fleet):
        """Return last effective travel warp recorded on fleet state."""
        if not fleet or not isinstance(fleet, Fleet):
            return None
        try:
            return self._effective_travel_warp(
                getattr(fleet, 'travel_warp', 0),
                getattr(fleet, 'warp_advantage', 0.0),
            )
        except (TypeError, ValueError):
            return 0

    def _fleet_warp_advantage(self, fleet):
        """Return stored per-fleet warp advantage."""
        if not fleet or not isinstance(fleet, Fleet):
            return 0.0
        return self._fleet_warp_advantage_from_data(getattr(fleet, 'warp_advantage', 0.0))

    @staticmethod
    def _fleet_warp_advantage_from_data(value):
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _effective_travel_warp(self, base_warp, warp_advantage):
        """Return displayed travel warp, including fleet warp advantage."""
        try:
            speed = max(0, int(base_warp or 0))
        except (TypeError, ValueError):
            return 0
        if speed <= 0 or speed == WORMHOLE_WARPFACTOR:
            return speed
        effective = max(0.0, float(speed) + self._fleet_warp_advantage_from_data(warp_advantage))
        if abs(effective - round(effective)) < 1e-9:
            return int(round(effective))
        return effective

    @staticmethod
    def _format_warp_value(value):
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 'Unknown'
        if abs(numeric - round(numeric)) < 1e-9:
            return str(int(round(numeric)))
        formatted = '%.2f' % numeric
        return formatted.rstrip('0').rstrip('.')

    def _format_signed_warp_advantage(self, value):
        try:
            numeric = float(value or 0.0)
        except (TypeError, ValueError):
            return ''
        if abs(numeric) < 1e-9:
            return ''
        sign = '+' if numeric > 0 else '-'
        return '%s%s' % (sign, self._format_warp_value(abs(numeric)))

    def _has_advanced_scanner_coverage(self, x, y):
        """Return True when player has advanced scanner visibility at location."""
        if not self.player:
            return False
        if getattr(self.game, 'no_scanners', False):
            return False
        return position_in_scanner_range(
            x,
            y,
            self._scanner_sources,
            range_key='advanced',
        )

    def _display_name_for_target(self, obj, target_type=None):
        """Return target display name with scanner concealment rules applied."""
        if not obj:
            return ''
        target_type = target_type or self._get_target_type(obj)
        if target_type == 'fleet':
            if self.spectator_mode or self.admin_view or not self.player:
                return obj.name
            if obj.player_id == self.player.id:
                return obj.name
            if getattr(self.game, 'no_scanners', False):
                return obj.name
            report_data = self._get_cached_report_data(obj, 'fleet')
            if report_data:
                return self._reported_object_name(obj, 'fleet', report_data)
            if self._has_advanced_scanner_coverage(obj.x, obj.y):
                return obj.name
            return format_basic_unknown_fleet_name(obj)
        if target_type == 'salvage':
            return self._salvage_display_name(obj)
        return obj.name or f"{obj.__class__.__name__} {obj.id}"

    def _primary_star_for_location(self, stars):
        """Return canonical primary star (homeworld first, then id order)."""
        if not stars:
            return None
        homeworld_id = self.player.homeworld_id if self.player else None
        if homeworld_id:
            for star in stars:
                if star.id == homeworld_id:
                    return star
        return sorted(
            stars,
            key=lambda star: (
                str(getattr(star, 'short_id', '') or ''),
                int(getattr(star, 'id', 0) or 0),
            ),
        )[0]

    def _decorate_target(self, target):
        """Attach shared display and sort metadata to a target dict."""
        data = dict(target)
        data['display_label'] = self._format_target_display(data)
        return data

    def _target_sort_key(self, target):
        """Return canonical ordering for detail selectors and target dropdowns."""
        target_type = target.get('type')
        if target_type == 'star':
            return (
                0,
                0 if target.get('is_homeworld') else 1,
                str(target.get('short_id') or ''),
                str(target.get('name') or ''),
            )
        if target_type == 'fleet':
            return (
                1 if target.get('is_owned') and not target.get('is_future') else
                2 if not target.get('is_owned') and not target.get('is_future') else
                3,
                0,
                str(target.get('short_id') or ''),
                str(target.get('name') or ''),
            )
        if target_type == 'salvage':
            return (4, 0, str(target.get('short_id') or ''), str(target.get('name') or ''))
        if target_type == 'anomaly':
            return (5, 0, str(target.get('short_id') or ''), str(target.get('name') or ''))
        if target_type == 'space':
            return (6, 0, '', str(target.get('name') or ''))
        return (7, 0, str(target.get('short_id') or ''), str(target.get('name') or ''))

    def _sort_targets(self, targets):
        """Return targets in stable UI order."""
        return sorted(targets, key=self._target_sort_key)

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
        raw_multiplier = getattr(self.player.race_type, 'population_growth_multiplier', 1.0)
        if raw_multiplier is None:
            raw_multiplier = 1.0
        factor *= float(
            raw_multiplier
        )
        if factor > 0 and bool(getattr(self.player.race_type, 'is_mechanical', False)):
            factor = 0
        current = self.selected_obj.colonists
        new_pop = apply_population_change(current, factor)
        if factor > 0 and population_growth_uses_surface_resources(self.player):
            limited_growth, _, _ = limit_population_growth_by_surface_resources(
                self.selected_obj,
                new_pop - current,
            )
            new_pop = current + limited_growth
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
        report_star = self._build_report_star_for_habitability(data)
        if report_star is None:
            return None
        return calculate_habitability_factor(self.player, report_star) >= 0

    def _capacity_from_report(self, data):
        """Estimate carrying capacity from cached environmental report data."""
        report_star = self._build_report_star_for_habitability(data)
        if report_star is None:
            return None
        return effective_capacity(self.player, report_star)

    def _build_report_star_for_habitability(self, data):
        """Build a lightweight star object for habitability-only calculations."""
        if not self.player:
            return None
        for env in ['gravity', 'temperature', 'radiation']:
            if env not in data:
                return None

        return type('ReportStar', (), {
            'gravity': data['gravity'],
            'temperature': data['temperature'],
            'radiation': data['radiation'],
            'base_capacity': getattr(self.selected_obj, 'base_capacity', 1),
            # Cached reports may omit infrastructure; these defaults keep the
            # shared rules callable without leaking extra report detail.
            'colonists': data.get('colonists', 0),
            'mines': data.get('mines', 0),
            'factories': data.get('factories', 0),
            'labs': data.get('labs', 0),
            'defenses': data.get('defenses', 0),
            'shipyards': data.get('shipyards', 0),
            'buildpoints_consumed': data.get('buildpoints_consumed', 0),
        })()

    def get_object_name(self):
        if isinstance(self.selected_obj, Salvage):
            return self._salvage_display_name(self.selected_obj)
        if self.selected_obj.name is None or len(self.selected_obj.name) == 0:
            return "%s %i" % (self.selected_obj.__class__.__name__, self.selected_obj.id)
        return self.selected_obj.name

    def get_object_player(self):
        """Return player display string as 'race name (username)' or None."""
        player = self.selected_obj.player
        if player:
            username = player.account.alias if player.account else 'Unknown'
            return '%s (%s)' % (player.name, username)
        if (
            isinstance(self.selected_obj, Star) and
            self._star_has_leftover_infrastructure(self.selected_obj)
        ):
            return 'Abandoned'
        if isinstance(self.selected_obj, Fleet):
            return 'Abandoned'
        return None

    def _format_report_owner_display(self, player_name):
        """Format report owner as 'Race (Account)' when possible."""
        if not player_name:
            return None
        if player_name == 'Abandoned':
            return player_name
        if ' (' in player_name and player_name.endswith(')'):
            return player_name
        player = self.game.players.select_related('account').filter(name=player_name).order_by('id').first()
        if not player:
            return player_name
        alias = player.account.alias if player.account else 'Unknown'
        return '%s (%s)' % (player.name, alias)

    @staticmethod
    def _star_has_leftover_infrastructure(star):
        if not star:
            return False
        infra_fields = ('mines', 'factories', 'labs', 'defenses', 'shipyards')
        return any(int(getattr(star, field, 0) or 0) > 0 for field in infra_fields)

    def find_all_at_coordinates(self, x, y):
        x = int(x)
        y = int(y)
        stars = self.game.stars.filter(x=x, y=y).all()
        fleets = self.game.fleets.filter(x=x, y=y).all()
        salvages = self._visible_salvages_qs().filter(x=x, y=y).all()
        anomalies = self.game.anomalys.filter(x=x, y=y).all()
        visible_fleets = []
        if self.spectator_mode or self.admin_view:
            visible_fleets = list(fleets)
        elif self.player:
            for fleet in fleets:
                if fleet_visible_to_player(fleet, self.player, sources=self._scanner_sources):
                    visible_fleets.append(fleet)
        self.at_cursor = list(chain(stars, visible_fleets, salvages, anomalies))
        return self.at_cursor

    def find_selected_from_coordinates(self, x, y):
        if not self.at_cursor:
            self.selected_obj = None
            return self.selected_obj
        stars = [obj for obj in self.at_cursor if isinstance(obj, Star)]
        if stars:
            self.selected_obj = self._primary_star_for_location(stars)
        else:
            self.selected_obj = self.at_cursor[0]
        return self.selected_obj

    def process_selected(self, selected):
        if selected:
            short_id = selected.lower()
            self.selected_obj = (
                Star.objects.filter(game=self.game, short_id=short_id).first() or
                Fleet.objects.filter(game=self.game, short_id=short_id).first() or
                Salvage.objects.filter(game=self.game, short_id=short_id).first() or
                Anomaly.objects.filter(game=self.game, short_id=short_id).first()
            )
            if isinstance(self.selected_obj, Salvage) and not self._is_salvage_visible(self.selected_obj):
                self.selected_obj = None
            if self.selected_obj:
                self.check_selected()
        return self.selected_obj

    def _visible_salvages_qs(self):
        if self.spectator_mode or self.admin_view:
            return self.game.salvages.all()
        if not self.player:
            return self.game.salvages.none()
        if getattr(self.game, 'no_scanners', False):
            return self.game.salvages.all()
        return self.game.salvages.filter(id__in=self._reported_salvage_ids)

    def _is_salvage_visible(self, salvage):
        if salvage is None:
            return False
        if self.spectator_mode or self.admin_view:
            return True
        if not self.player:
            return False
        if getattr(self.game, 'no_scanners', False):
            return True
        return salvage.id in self._reported_salvage_ids

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
        elif isinstance(obj, Anomaly):
            return 'anomaly'
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
            is_ignored = player_ignores_environment(self.player, env_name)
            data['hab_min_percent'] = (hab_min / 2.0) * 100
            data['hab_max_percent'] = (hab_max / 2.0) * 100
            data['hab_center_percent'] = (center / 2.0) * 100
            data['is_ignored'] = is_ignored
            data['is_habitable'] = habitability_value_for_environment(
                self.player,
                env_name,
                value,
            ) >= 0
            if is_ignored:
                data['bar_style'] = 'background: #00aa00;'
            else:
                data['bar_style'] = (
                    'background: linear-gradient(to right, '
                    '#400000 0%, '
                    f'#400000 {data["hab_min_percent"]:.1f}%, '
                    f'#00ff00 {data["hab_center_percent"]:.1f}%, '
                    f'#400000 {data["hab_max_percent"]:.1f}%, '
                    '#400000 100%);'
                )
        return data

    def _resource_label(self, resource_key):
        if resource_key in SECRET_RESOURCE_KEYS:
            discovered = False
            if (self.spectator_mode or self.admin_view) and self.viewer_account:
                discovered = bool(getattr(self.viewer_account, f'discovered_{resource_key}', False))
            elif self.player:
                discovered = bool(getattr(self.player, f'discovered_{resource_key}', False))
            elif self.viewer_account:
                discovered = bool(getattr(self.viewer_account, f'discovered_{resource_key}', False))
            return get_secret_resource_label(resource_key, discovered)
        return self.RESOURCE_LABELS.get(resource_key, str(resource_key).title())

    def build_resource_detail(self):
        resources = None
        if self.selected_obj and isinstance(self.selected_obj, Star):
            mining_rates = self._build_resource_mining_rates()
            resources = {}
            for key in ALL_RESOURCE_KEYS:
                yield_val = int(getattr(self.selected_obj, f'{key}_yield', 0) or 0)
                surface_val = int(getattr(self.selected_obj, f'{key}_inventory', 0) or 0)
                if key in SECRET_RESOURCE_KEYS and yield_val <= 0 and surface_val <= 0:
                    continue
                resources[key] = {
                    'label': self._resource_label(key),
                    'yield': yield_val,
                    'surface': surface_val,
                    'mining_rate': mining_rates.get(key, 0),
                }
        return resources

    def _build_resource_mining_rates(self):
        """Build per-resource expected mining output for one year."""
        rates = {key: 0 for key in ALL_RESOURCE_KEYS}
        if not self.selected_obj or not isinstance(self.selected_obj, Star):
            return rates
        if not self.player or self.selected_obj.player != self.player:
            return rates

        star = self.selected_obj
        total_yield = sum(
            int(getattr(star, f'{key}_yield', 0) or 0) for key in ALL_RESOURCE_KEYS
        )
        if total_yield <= 0 or star.mines <= 0:
            return rates

        staffing_ratio = calculate_staffing_ratio(star)
        if staffing_ratio <= 0:
            return rates

        productivity = calculate_productivity_multiplier(staffing_ratio)
        total_extraction = star.mines * KT_PER_MINE * productivity

        for key in ALL_RESOURCE_KEYS:
            yield_val = int(getattr(star, f'{key}_yield', 0) or 0)
            if yield_val <= 0:
                rates[key] = 0
            else:
                rates[key] = int(total_extraction * yield_val / total_yield)
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
            scanner_display = None
            administration_level = 0
            if is_owned:
                colony_defense_level = get_player_colony_defense_level(self.player)
                administration_level = int(
                    get_player_administration_profile(self.player).get('level', 0)
                    or 0
                )
                defense_multiplier = 2.0 ** max(0.0, colony_defense_level)
                effective_base_defenses = calculate_effective_defenses(
                    self.selected_obj
                )
                effective_defenses = int(
                    effective_base_defenses * defense_multiplier
                )
                modifier = int(round(colony_defense_level * 10.0))
                defenses_tooltip = f"{effective_defenses}({modifier:+d})"
                try:
                    raw_multiplier = getattr(self.player.race_type, 'defence_multiplier', 1.0)
                    if raw_multiplier is None:
                        raw_multiplier = 1.0
                    race_multiplier = float(
                        raw_multiplier
                    )
                except (TypeError, ValueError):
                    race_multiplier = 1.0
                if abs(race_multiplier - 1.0) >= 1e-9:
                    percent = int(round((race_multiplier - 1.0) * 100.0))
                    defenses_tooltip = f"{defenses_tooltip} ({percent:+d}%)"
                basic_scan, advanced_scan = get_player_colony_scanner_ranges(self.player)
                scanner_display = self._format_scanner_range(
                    basic_scan,
                    advanced_scan,
                    self._race_multiplier_percent_suffix(self.player, 'scan_multiplier'),
                )
            infrastructure = {
                'Mines': self.selected_obj.mines,
                'Factories': self.selected_obj.factories,
                'FactoriesBP': calculate_available_buildpoints(self.selected_obj),
                'FactoriesTooltip': self._build_factories_tooltip(self.selected_obj),
                'Labs': self.selected_obj.labs,
                'LabsRP': calculate_available_researchpoints(self.selected_obj),
                'Scanners': scanner_display,
                'Defenses': self.selected_obj.defenses,
                'DefensesTooltip': defenses_tooltip,
                'Shipyards': self.selected_obj.shipyards,
                'Administration': (
                    'Level %s' % administration_level
                    if self.selected_obj.has_administration and administration_level > 0
                    else None
                ),
                'Jobs': {'count': jobs, 'employment': employment},
            }
        return infrastructure

    def _build_factories_tooltip(self, star):
        base_text = f"{calculate_available_buildpoints(star)}BP/Year"
        owner = getattr(star, 'player', None)
        if not owner or not getattr(owner, 'race_type', None):
            return base_text
        try:
            raw_multiplier = getattr(owner.race_type, 'manufacturing_multiplier', 1.0)
            if raw_multiplier is None:
                raw_multiplier = 1.0
            multiplier = float(
                raw_multiplier
            )
        except (TypeError, ValueError):
            multiplier = 1.0
        if abs(multiplier - 1.0) < 1e-9:
            return base_text
        percent = int(round((multiplier - 1.0) * 100.0))
        return f"{base_text} ({percent:+d}%)"

    def get_production_orders(self):
        """Get production orders for selected star."""
        if not self.selected_obj or not isinstance(self.selected_obj, Star):
            return []
        if not self.player or self.selected_obj.player != self.player:
            return []
        cost_map = get_player_production_costs(self.player)
        profile = get_player_terraforming_profile(self.player)
        rate_percent = int(round(profile.get('rate', 0.0) * 100.0))
        orders = []
        for o in self.selected_obj.production_orders.order_by('position'):
            cost = cost_map.get(o.order_type, {})
            if o.order_type.startswith('TERRAFORM_'):
                display = format_terraform_order_label(o.order_type, rate_percent)
            else:
                display = o.get_order_type_display()
            
            # Calculate progress based on what has actually been spent
            colonist_cost = int(cost.get('colonists', 0) or 0)
            labor_cost = cost.get('bp', 0) or colonist_cost
            resource_cost = sum(cost.get(key, 0) for key in ALL_RESOURCE_KEYS)
            spent_resource_total = sum(int(getattr(o, f'spent_{key}', 0) or 0) for key in ALL_RESOURCE_KEYS)
            
            if labor_cost > 0 and resource_cost > 0:
                # Items with both labor and resources: each contributes 50%
                resource_progress = min(
                    (spent_resource_total / resource_cost) * 50, 50
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
                    (spent_resource_total / resource_cost) * 100, 100
                )
                labor_progress = 0
                total_progress = resource_progress
            else:
                # No costs (shouldn't happen)
                resource_progress = labor_progress = total_progress = 0
            
            orders.append({
                'short_id': o.short_id,
                'type': o.order_type,
                'display': display,
                'quantity': o.quantity,
                'completed': o.completed,
                'repeat': o.repeat,
                'repeat_allowed': o.order_type not in ADMINISTRATION_ONE_OFF_ORDER_TYPES,
                'added_by_micromanager': bool(o.added_by_micromanager),
                'progress_percent': min(int(total_progress), 100),
                'resource_progress': min(int(resource_progress), 50 if labor_cost > 0 and resource_cost > 0 else 100),
                'labor_progress': min(int(labor_progress), 50 if resource_cost > 0 and labor_cost > 0 else 100),
                'has_labor': labor_cost > 0,
                'cost': {
                    'bp': cost.get('bp', 0),
                    **{key: cost.get(key, 0) for key in ALL_RESOURCE_KEYS},
                    'colonists': colonist_cost,
                },
                'spent': {
                    'bp': o.spent_bp,
                    **{key: self.format_kt(getattr(o, f'spent_{key}', 0)) for key in ALL_RESOURCE_KEYS},
                },
                'remaining': {
                    'bp': cost.get('bp', 0) - o.spent_bp,
                    **{key: self.format_kt(cost.get(key, 0) - int(getattr(o, f'spent_{key}', 0) or 0)) for key in ALL_RESOURCE_KEYS},
                },
            })
        return orders

    def get_available_production_orders(self):
        """Return available production orders for the selected star."""
        if not self.selected_obj or not isinstance(self.selected_obj, Star):
            return []
        if not self.player or self.selected_obj.player != self.player:
            return []
        orders = get_player_available_production_orders(self.player, self.selected_obj)
        cost_map = get_player_production_costs(self.player)
        for option in orders:
            order_type = option.get('value')
            cost = cost_map.get(order_type, {}) if order_type else {}
            option['repeat_allowed'] = bool(
                option.get('repeat_allowed', True)
            )
            option['cost'] = {
                'bp': int(cost.get('bp', 0) or 0),
                **{key: int(cost.get(key, 0) or 0) for key in ALL_RESOURCE_KEYS},
                'colonists': int(cost.get('colonists', 0) or 0),
            }
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
            if kind in ['star', 'fleet', 'salvage', 'anomaly'] and obj:
                target = self._display_name_for_target(obj, kind)
                if kind == 'fleet':
                    link_x = None
                    link_y = None
                    if self._is_fleet_currently_visible(obj):
                        link_x = obj.x
                        link_y = obj.y
                    else:
                        link_x, link_y = self._fleet_report_coordinates(obj)
                    if link_x is not None and link_y is not None:
                        target_link = f'?x={link_x}&y={link_y}&sel={obj.short_id}&locate=1'
                    else:
                        target_link = f'?sel={obj.short_id}'
                else:
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
            repeat_allowed = o.order_type not in ['COLONISE', 'MERGE', 'SCUTTLE', 'GIVE']
            order_data = {
                'short_id': o.short_id,
                'target': target,
                'target_link': target_link,
                'target_kind': kind,
                'target_short_id': getattr(obj, 'short_id', ''),
                'target_x': x,
                'target_y': y,
                'warpfactor': o.warpfactor,
                'eta_years': eta_years,
                'repeat': o.repeat,
                'repeat_allowed': repeat_allowed,
                'added_by_micromanager': bool(
                    getattr(o, 'added_by_micromanager', False)
                ),
                'order_type': o.order_type,
                'transfer_player_name': (
                    o.transfer_player.name if getattr(o, 'transfer_player_id', None) else None
                ),
                'transfer_player_short_id': (
                    o.transfer_player.short_id if getattr(o, 'transfer_player_id', None) else ''
                ),
                'patrol_radius': o.patrol_radius,
                'intercept_speed': o.intercept_speed,
                'mine_until_full': bool(o.mine_until_full),
                'bomb_until': o.bomb_until,
                'remotemine_focus': getattr(o, 'remotemine_focus', '') or '',
                'transfer_type': o.transfer_type,
                'transfer_ironium': o.transfer_ironium,
                'transfer_boranium': o.transfer_boranium,
                'transfer_germanium': o.transfer_germanium,
                'transfer_resource_x': o.transfer_resource_x,
                'transfer_resource_y': o.transfer_resource_y,
                'transfer_resource_z': o.transfer_resource_z,
                'transfer_colonists': o.transfer_colonists,
                'transfer_fuel': o.transfer_fuel,
                'target_star': obj if kind == 'star' else None,  # For template access
                'target_salvage': obj if kind == 'salvage' else None,  # For template access
            }

            if o.order_type == 'REMOTEMINE':
                focus_raw = (getattr(o, 'remotemine_focus', '') or '').strip()
                focus_keys = [
                    key.strip().lower()
                    for key in focus_raw.replace(';', ',').split(',')
                    if key.strip()
                ]
                focus_keys = [key for key in focus_keys if key in ALL_RESOURCE_KEYS]
                focus_labels = [self._resource_label(key) for key in focus_keys]
                if focus_labels:
                    label_text = ', '.join(focus_labels)
                    if o.mine_until_full:
                        order_data['remotemine_tooltip'] = f'Mine {label_text} until full'
                    else:
                        order_data['remotemine_tooltip'] = f'Mine {label_text}'
                else:
                    order_data['remotemine_tooltip'] = (
                        'Mine all until full' if o.mine_until_full else 'Mine all'
                    )
            elif o.order_type == 'BOMB':
                bomb_until = (o.bomb_until or '').upper()
                if bomb_until == 'DEFENSES_ZERO':
                    order_data['bomb_tooltip'] = 'Bomb until 0 defenses'
                elif bomb_until == 'ONCE':
                    order_data['bomb_tooltip'] = 'Bomb once'
                else:
                    order_data['bomb_tooltip'] = 'Bomb until 0 colonists'

            orders.append(order_data)
        return orders

    def get_transfer_recipients(self):
        """Return possible fleet transfer recipients for the selected fleet."""
        if not self.selected_obj or not isinstance(self.selected_obj, Fleet):
            return []
        if not self.player or self.selected_obj.player != self.player:
            return []
        from dj4xol.diplomacy import has_encountered_player

        recipients = [{
            'value': '',
            'label': 'Abandoned',
        }]
        others = self.game.players.exclude(id=self.player.id).exclude(defeated=True).order_by('name', 'id')
        for other in others:
            if not has_encountered_player(self.player, other):
                continue
            alias = other.account.alias if getattr(other, 'account', None) else 'Unknown'
            recipients.append({
                'value': other.short_id,
                'label': '%s (%s)' % (other.name, alias),
            })
        return recipients

    def get_fleet_cargo(self, include_cargo=False):
        """Get cargo details for selected fleet."""
        if not self.selected_obj or not isinstance(self.selected_obj, Fleet):
            return None

        # Always expose composition for visible fleets (own or observed).
        # Cargo/inventory remains owner-only.
        cargo = self._build_fleet_composition(self.selected_obj)
        cargo['max_safe_warp'] = getattr(self.selected_obj, 'max_safe_warp', None)
        cargo['max_cloaked_warp'] = getattr(self.selected_obj, 'max_cloaked_warp', -1)
        cargo['fuel_factory_mg_per_year'] = getattr(
            self.selected_obj, 'fuel_factory_mg_per_year', 0.0
        )
        cargo['fuel_factory_max_warp'] = getattr(
            self.selected_obj, 'fuel_factory_max_warp', -1
        )
        cargo['wormhole_fuel_per_ly'] = getattr(
            self.selected_obj, 'wormhole_fuel_per_ly', 5.0
        )
        cargo['move_default_warp'] = self._fleet_default_move_warp(self.selected_obj)
        cargo['move_default_cloaked'] = self._fleet_move_speed_is_cloaked(
            self.selected_obj,
            cargo['move_default_warp'],
        )
        cargo['move_default_fuel_factory_active'] = (
            self._fleet_move_speed_has_fuel_factory(
                self.selected_obj,
                cargo['move_default_warp'],
            )
        )
        cargo['intercept_default_cloaked'] = self._fleet_move_speed_is_cloaked(
            self.selected_obj,
            cargo['max_safe_warp'],
        )
        cargo['intercept_default_fuel_factory_active'] = (
            self._fleet_move_speed_has_fuel_factory(
                self.selected_obj,
                cargo['max_safe_warp'],
            )
        )
        if include_cargo or (self.player and self.selected_obj.player == self.player):
            cargo.update({
                'capacity': self.selected_obj.cargo_capacity,
                'used': self.selected_obj.cargo_used,
                'remaining': self.selected_obj.cargo_remaining,
                'fuel': self.selected_obj.fuel,
                'max_fuel': self.selected_obj.max_fuel,
                'ironium': self.selected_obj.ironium_inventory,
                'boranium': self.selected_obj.boranium_inventory,
                'germanium': self.selected_obj.germanium_inventory,
                'resource_x': self.selected_obj.resource_x_inventory,
                'resource_y': self.selected_obj.resource_y_inventory,
                'resource_z': self.selected_obj.resource_z_inventory,
                'colonists': self.selected_obj.colonists,
            })
        return cargo

    def get_fleet_capabilities(
        self,
        include_scanners=True,
        allow_foreign_levels=False,
    ):
        """Get capability details for selected fleet."""
        if not self.selected_obj or not isinstance(self.selected_obj, Fleet):
            return None
        if (
            not allow_foreign_levels and
            self.player and
            self.selected_obj.player_id != self.player.id
        ):
            return None
        return self._build_fleet_capabilities(
            getattr(self.selected_obj, 'max_safe_warp', None),
            getattr(self.selected_obj, 'warp_advantage', 0.0),
            getattr(self.selected_obj, 'max_cloaked_warp', -1),
            bool(getattr(self.selected_obj, 'advanced_cloak', False)),
            self.selected_obj.has_bombs,
            self.selected_obj.has_miners,
            getattr(self.selected_obj, 'fuel_factory_mg_per_year', 0.0),
            bool(self.selected_obj.has_wormhole_drive),
            getattr(self.selected_obj, 'basic_scanner_range', 0),
            getattr(self.selected_obj, 'advanced_scanner_range', 0),
            scanner_suffix=self._race_multiplier_percent_suffix(
                self.selected_obj.player if self.selected_obj.player == self.player else None,
                'scan_multiplier',
            ),
            include_scanners=include_scanners,
        )

    def _can_show_fleet_level_data(self, fleet):
        """Return True when current viewer can see foreign fleet levels."""
        if not fleet or not isinstance(fleet, Fleet):
            return False
        if self.admin_view:
            return True
        if not self.player:
            return False
        if fleet.player_id == self.player.id:
            return True
        return self._has_advanced_scanner_coverage(fleet.x, fleet.y)

    def _build_fleet_composition(self, fleet):
        """Build non-cargo fleet composition fields."""
        offense_mod = int(round(float(fleet.offense_level) * 10.0))
        defense_mod = int(round(float(fleet.defense_level) * 10.0))
        return {
            'integrity': fleet.integrity,
            'ship_count': fleet.ship_count,
            'offense_modifier': f'{offense_mod:+d}',
            'defense_modifier': f'{defense_mod:+d}',
            'has_bombs': fleet.has_bombs,
            'has_miners': fleet.has_miners,
            'has_fuel_factory': bool(
                getattr(fleet, 'fuel_factory_mg_per_year', 0.0)
            ),
            'fuel_factory_mg_per_year': getattr(
                fleet, 'fuel_factory_mg_per_year', 0.0
            ),
            'fuel_factory_max_warp': getattr(
                fleet, 'fuel_factory_max_warp', -1
            ),
            'has_wormhole_drive': bool(fleet.has_wormhole_drive),
        }

    def _build_fleet_capabilities(
        self,
        max_safe_warp,
        warp_advantage,
        max_cloaked_warp,
        advanced_cloak,
        bombs,
        miners,
        fuel_factory_mg_per_year,
        has_wormhole_drive,
        basic_scanner_range,
        advanced_scanner_range,
        scanner_suffix='',
        include_scanners=False,
    ):
        """Build list of capability label/value pairs."""
        capabilities = []
        if max_safe_warp is not None:
            max_warp_value = str(max_safe_warp)
            try:
                positive_advantage = max(0.0, float(warp_advantage or 0.0))
            except (TypeError, ValueError):
                positive_advantage = 0.0
            if positive_advantage > 0.0:
                max_warp_value = '%s %s' % (
                    max_warp_value,
                    self._format_signed_warp_advantage(positive_advantage),
                )
            capabilities.append({
                'label': 'Max Warp',
                'value': max_warp_value,
            })
        cloak_capability = self._fleet_cloak_capability_value(
            max_cloaked_warp,
            advanced_cloak,
        )
        if cloak_capability:
            capabilities.append({
                'label': 'Stealth',
                'value': cloak_capability,
            })
        if bombs:
            capabilities.append({
                'label': 'Bombs',
                'value': str(bombs).title(),
            })
        if miners:
            capabilities.append({
                'label': 'Miners',
                'value': str(miners).title(),
            })
        fuel_factory_display = self._format_fuel_factory_output(
            fuel_factory_mg_per_year
        )
        if fuel_factory_display:
            capabilities.append({
                'label': 'Fuel Factory',
                'value': fuel_factory_display,
            })
        if has_wormhole_drive:
            capabilities.append({
                'label': 'Wormhole Drive',
                'value': 'Yes',
            })
        if include_scanners:
            scanner_display = self._format_scanner_range(
                basic_scanner_range,
                advanced_scanner_range,
                scanner_suffix,
            )
            if scanner_display:
                capabilities.append({
                    'label': 'Scanner Range',
                    'value': scanner_display,
                })
        return capabilities or None

    def _fleet_cloak_capability_value(self, max_cloaked_warp, advanced_cloak):
        try:
            max_cloaked_warp = int(max_cloaked_warp)
        except (TypeError, ValueError):
            max_cloaked_warp = -1
        if advanced_cloak:
            return 'Advanced'
        if max_cloaked_warp >= 0:
            return 'Basic'
        return None

    def _format_fuel_factory_output(self, fuel_factory_mg_per_year):
        try:
            fuel_factory_mg_per_year = float(fuel_factory_mg_per_year or 0.0)
        except (TypeError, ValueError):
            fuel_factory_mg_per_year = 0.0
        if fuel_factory_mg_per_year <= 0.0:
            return None
        return '{0:g} mg/y'.format(fuel_factory_mg_per_year)

    def _fleet_default_move_warp(self, fleet):
        if not fleet:
            return None
        try:
            max_safe_warp = int(getattr(fleet, 'max_safe_warp', 0) or 0)
        except (TypeError, ValueError):
            max_safe_warp = 0
        try:
            max_cloaked_warp = int(getattr(fleet, 'max_cloaked_warp', -1) or 0)
        except (TypeError, ValueError):
            max_cloaked_warp = -1
        if max_cloaked_warp >= 0:
            return min(max_safe_warp, max_cloaked_warp)
        return max_safe_warp

    def _fleet_move_speed_is_cloaked(self, fleet, speed):
        if not fleet:
            return False
        try:
            speed = int(speed)
        except (TypeError, ValueError):
            return False
        try:
            max_cloaked_warp = int(getattr(fleet, 'max_cloaked_warp', -1) or 0)
        except (TypeError, ValueError):
            max_cloaked_warp = -1
        return bool(getattr(fleet, 'player_id', None)) and max_cloaked_warp >= 0 and speed <= max_cloaked_warp

    def _fleet_move_speed_has_fuel_factory(self, fleet, speed):
        if not fleet:
            return False
        try:
            speed = int(speed)
        except (TypeError, ValueError):
            return False
        try:
            fuel_factory_rate = float(
                getattr(fleet, 'fuel_factory_mg_per_year', 0.0) or 0.0
            )
        except (TypeError, ValueError):
            fuel_factory_rate = 0.0
        try:
            fuel_factory_max_warp = int(
                getattr(fleet, 'fuel_factory_max_warp', -1)
            )
        except (TypeError, ValueError):
            fuel_factory_max_warp = -1
        return fuel_factory_rate > 0.0 and (
            fuel_factory_max_warp >= 0 and speed <= fuel_factory_max_warp
        )

    def _format_scanner_range(self, basic, advanced, suffix=''):
        """Format scanner range display or return None when no scanners are present."""
        try:
            basic_val = int(basic or 0)
        except (TypeError, ValueError):
            basic_val = 0
        try:
            advanced_val = int(advanced or 0)
        except (TypeError, ValueError):
            advanced_val = 0
        if basic_val <= 0 and advanced_val <= 0:
            return None
        suffix = str(suffix or '')
        return f'{basic_val}ly/{advanced_val}ly{suffix}'

    def _race_multiplier_percent_suffix(self, player, attr_name):
        if not player:
            return ''
        race_type = getattr(player, 'race_type', None)
        raw = getattr(race_type, attr_name, 1.0)
        if raw is None:
            return ''
        try:
            multiplier = float(raw)
        except (TypeError, ValueError):
            return ''
        if abs(multiplier - 1.0) < 1e-9:
            return ''
        percent = int(round((multiplier - 1.0) * 100.0))
        return f' ({percent:+d}%)'

    def build_fleet_inventory(self, allow_foreign=False):
        """Build fleet cargo inventory data for progress bar display."""
        if not self.selected_obj or not isinstance(self.selected_obj, Fleet):
            return None
        if not allow_foreign:
            if not self.player or self.selected_obj.player != self.player:
                return None
        
        capacity = self.selected_obj.cargo_capacity
        fuel_cap = max(0.0, float(self.selected_obj.max_fuel))
        inventory = {
            'fuel': dict(self._build_cargo_data(self.selected_obj.fuel, fuel_cap, 'mg'), label='Fuel'),
            'ironium': dict(self._build_cargo_data(self.selected_obj.ironium_inventory, capacity, 'kt'), label='Ironium'),
            'boranium': dict(self._build_cargo_data(self.selected_obj.boranium_inventory, capacity, 'kt'), label='Boranium'),
            'germanium': dict(self._build_cargo_data(self.selected_obj.germanium_inventory, capacity, 'kt'), label='Germanium'),
            'colonists': dict(self._build_cargo_data(self.selected_obj.colonists, capacity, 'k'), label='Colonists'),
        }
        for key in SECRET_RESOURCE_KEYS:
            amount = int(getattr(self.selected_obj, f'{key}_inventory', 0) or 0)
            if amount <= 0:
                continue
            inventory[key] = dict(
                self._build_cargo_data(amount, capacity, 'kt'),
                label=self._resource_label(key),
            )
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
        items = []
        for key in ALL_RESOURCE_KEYS:
            amount = int(getattr(self.selected_obj, f'{key}_inventory', 0) or 0)
            if amount <= 0:
                continue
            items.append({
                'label': self._resource_label(key),
                'amount': amount,
            })
        return {
            'items': items,
            'total': self.selected_obj.total_minerals,
            'composition_unknown': False,
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
            include_anomalies=True,
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
            display_name = self._format_target_display(target)
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
        include_anomalies=False,
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
        homeworld_id = self.player.homeworld_id if self.player else None
        seen = set()

        def add_target(target):
            key = (target.get('type'), target.get('short_id'))
            if key in seen:
                return
            seen.add(key)
            targets.append(self._decorate_target(target))

        stars_at_location = []
        anomalies_at_location = []
        if include_stars:
            stars_at_location = list(self.game.stars.filter(x=x, y=y))
            for star in stars_at_location:
                add_target({
                    'name': star.name,
                    'short_id': star.short_id,
                    'type': 'star',
                    'is_homeworld': bool(homeworld_id and star.id == homeworld_id),
                    'is_owned': bool(self.player and star.player_id == self.player.id),
                    'is_future': False,
                })

        if include_anomalies:
            anomalies_at_location = list(self.game.anomalys.filter(x=x, y=y))
            for anomaly in anomalies_at_location:
                add_target({
                    'name': anomaly.name,
                    'short_id': anomaly.short_id,
                    'type': 'anomaly',
                    'is_future': False,
                })

        if include_fleets:
            fleets_qs = self.game.fleets.filter(x=x, y=y)
            if fleet_player is not None:
                fleets_qs = fleets_qs.filter(player=fleet_player)
            if exclude_fleet_id is not None:
                fleets_qs = fleets_qs.exclude(id=exclude_fleet_id)
            for fleet in fleets_qs:
                if (
                    not self.admin_view and
                    not fleet_visible_to_player(
                        fleet,
                        self.player,
                        sources=self._scanner_sources,
                    )
                ):
                    continue
                add_target({
                    'name': self._display_name_for_target(fleet, 'fleet'),
                    'short_id': fleet.short_id,
                    'type': 'fleet',
                    'is_owned': bool(self.player and fleet.player_id == self.player.id),
                    'is_future': False,
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
            object_short_ids = [
                star.short_id for star in stars_at_location
            ] + [
                anomaly.short_id for anomaly in anomalies_at_location
            ]
            target_object_filter = None
            if object_short_ids:
                target_object_filter = models.Q(
                    target_kind='OBJECT',
                    target_short_id__in=object_short_ids,
                )

            location_filter = models.Q(x=x, y=y)
            combined_filter = location_filter
            if target_star_filter is not None:
                combined_filter = combined_filter | target_star_filter
            if target_object_filter is not None:
                combined_filter = combined_filter | target_object_filter
            orders_qs = orders_qs.filter(combined_filter)

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
                    if (
                        not self.admin_view and
                        not fleet_visible_to_player(
                            fleet,
                            self.player,
                            sources=self._scanner_sources,
                        )
                    ):
                        continue
                    add_target({
                        'name': self._display_name_for_target(fleet, 'fleet'),
                        'short_id': fleet.short_id,
                        'type': 'fleet',
                        'is_owned': bool(self.player and fleet.player_id == self.player.id),
                        'is_future': True,
                    })

        if include_salvage:
            for salvage in self._visible_salvages_qs().filter(x=x, y=y):
                add_target({
                    'name': salvage.name,
                    'short_id': salvage.short_id,
                    'type': 'salvage',
                    'total_minerals': salvage.total_minerals,
                    'is_future': False,
                })

        if include_empty and not targets:
            empty_space_name = self.format_empty_space(x, y)
            targets.append({
                'name': empty_space_name,
                'short_id': '',
                'type': 'space',
                'is_future': False,
                'display_label': self.format_empty_space(x, y),
            })

        return self._sort_targets(targets)

    def _format_target_display(self, target):
        """Return display name for a target, marking homeworlds."""
        if target.get('type') == 'star' and target.get('is_homeworld'):
            return f"{target['name']} (home)"
        if target.get('type') == 'star' and target.get('is_owned'):
            return f"{target['name']} (colony)"
        if target.get('type') == 'space':
            return target['name']
        return f"{target['name']} ({target['type'].title()})"
    
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
            return {
                'targets': [],
                'location': (0, 0),
                'display_mode': 'empty',
                'default_target': None,
                'resource_flags': {key: False for key in SECRET_RESOURCE_KEYS},
            }
        
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
        has_salvage = self._visible_salvages_qs().filter(x=effective_x, y=effective_y).exists()
        if not has_star and not has_salvage:
            if not any(target.get('type') == 'space' for target in targets):
                empty_space_name = DetailBuilder.format_empty_space(effective_x, effective_y)
                targets.insert(0, {
                    'name': empty_space_name,
                    'short_id': '',
                    'type': 'space',
                })

        resource_flags = {key: False for key in SECRET_RESOURCE_KEYS}
        if self.player and self.selected_obj.player == self.player:
            for key in SECRET_RESOURCE_KEYS:
                if int(getattr(self.selected_obj, f'{key}_inventory', 0) or 0) > 0:
                    resource_flags[key] = True
            for star in self.game.stars.filter(x=effective_x, y=effective_y):
                for key in SECRET_RESOURCE_KEYS:
                    if int(getattr(star, f'{key}_inventory', 0) or 0) > 0:
                        resource_flags[key] = True
            for fleet in self.game.fleets.filter(x=effective_x, y=effective_y, player=self.player):
                for key in SECRET_RESOURCE_KEYS:
                    if int(getattr(fleet, f'{key}_inventory', 0) or 0) > 0:
                        resource_flags[key] = True
            for salvage in self._visible_salvages_qs().filter(x=effective_x, y=effective_y):
                for key in SECRET_RESOURCE_KEYS:
                    if int(getattr(salvage, f'{key}_inventory', 0) or 0) > 0:
                        resource_flags[key] = True

        # Determine display mode and default target
        if not targets:
            return {
                'targets': [],
                'location': (effective_x, effective_y),
                'display_mode': 'empty',
                'default_target': None,
                'resource_flags': resource_flags,
            }
        if len(targets) == 1 and targets[0].get('type') == 'space':
            empty_space_name = DetailBuilder.format_empty_space(effective_x, effective_y)
            return {
                'targets': targets,
                'location': (effective_x, effective_y),
                'display_mode': 'empty',
                'default_target': empty_space_name,
                'resource_flags': resource_flags,
            }
        if len(targets) == 1:
            target = targets[0]
            display_name = self._format_target_display(target)
            return {
                'targets': targets,
                'location': (effective_x, effective_y),
                'display_mode': 'single',
                'default_target': display_name,
                'resource_flags': resource_flags,
            }
        return {
            'targets': targets,
            'location': (effective_x, effective_y),
            'display_mode': 'multiple',
            'default_target': targets[0],
            'resource_flags': resource_flags,
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

        targets = self._build_location_targets(
            effective_x,
            effective_y,
            include_stars=True,
            include_fleets=False,
            include_salvage=False,
            include_anomalies=False,
            include_empty=False,
            include_future_fleets=False,
        )
        targets = [target for target in targets if target.get('type') == 'star']

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
        targets = self._build_location_targets(
            effective_x,
            effective_y,
            include_stars=True,
            include_fleets=False,
            include_salvage=False,
            include_anomalies=False,
            include_empty=False,
            include_future_fleets=False,
        )
        targets = [target for target in targets if target.get('type') == 'star']

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
        targets = self._build_location_targets(
            effective_x,
            effective_y,
            include_stars=True,
            include_fleets=False,
            include_salvage=False,
            include_anomalies=False,
            include_empty=False,
            include_future_fleets=False,
        )
        stars_by_short_id = {
            star.short_id: star
            for star in self.game.stars.filter(x=effective_x, y=effective_y)
        }
        targets = [target for target in targets if target.get('type') == 'star']
        for target in targets:
            star = stars_by_short_id.get(target.get('short_id'))
            target['resource_keys'] = known_resource_keys(self.player, star)

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

    def get_remotemine_focus_options(self):
        """Return mineral focus options for advanced remote miners."""
        if not isinstance(self.selected_obj, Fleet):
            return []
        if not self.selected_obj.has_miners:
            return []
        if str(self.selected_obj.has_miners).strip().upper() != 'LARGE':
            return []

        options = []
        for key in BASE_MINERAL_KEYS:
            options.append({'key': key, 'label': self._resource_label(key)})
        if self.player:
            for key in SECRET_RESOURCE_KEYS:
                if getattr(self.player, f'discovered_{key}', False):
                    options.append({'key': key, 'label': self._resource_label(key)})
        return options

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
            display_name = self._format_target_display(target)
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

    def get_refuel_targets(self):
        """Get available same-location fleets for refuel orders."""
        if not isinstance(self.selected_obj, Fleet):
            return {
                'targets': [],
                'location': (0, 0),
                'display_mode': 'empty',
                'default_target': None,
            }

        if not self.player or self.selected_obj.player != self.player:
            return {
                'targets': [],
                'location': (0, 0),
                'display_mode': 'empty',
                'default_target': None,
            }

        effective_x, effective_y = self.get_fleet_effective_location()
        targets = self._build_location_targets(
            effective_x,
            effective_y,
            include_stars=False,
            include_fleets=True,
            include_salvage=False,
            include_empty=False,
            include_future_fleets=True,
            exclude_fleet_id=self.selected_obj.id,
            include_order_types=['MOVE', 'INTERCEPT', 'PATROL'],
        )
        targets = [target for target in targets if target.get('type') == 'fleet']
        stance_map = build_stance_map(self.player)
        target_short_ids = [target.get('short_id') for target in targets]
        fleet_player_map = {
            fleet.short_id: fleet.player
            for fleet in self.game.fleets.filter(short_id__in=target_short_ids)
            .select_related('player')
        }
        targets = [
            target for target in targets
            if player_can_refuel_fleet(
                self.player,
                fleet_player_map.get(target.get('short_id')),
                stance_map=stance_map,
            )
        ]

        if not targets:
            return {
                'targets': [],
                'location': (effective_x, effective_y),
                'display_mode': 'empty',
                'default_target': None,
            }
        if len(targets) == 1:
            return {
                'targets': targets,
                'location': (effective_x, effective_y),
                'display_mode': 'single',
                'default_target': targets[0],
            }
        return {
            'targets': targets,
            'location': (effective_x, effective_y),
            'display_mode': 'multiple',
            'default_target': targets[0],
        }
