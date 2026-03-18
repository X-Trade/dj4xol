from math import cos, sin, radians
from html import escape
from .models import Game, Player, Fleet, Star, Salvage, Anomaly, Report, PlayerStarMarker
from .anomaly_thumbnails import nebula_palette_from_thumbnail
from .scanners import (
    fleet_visible_to_player,
    get_scanner_sources_for_player,
    position_in_scanner_range,
)
from .turn import format_basic_hidden_salvage_name, format_basic_unknown_fleet_name

class StarMap():
    MAP_SCALE = 6
    MAP_BORDER = 10  # Border in light-years around the map
    MULTI_STAR_OFFSET = 0.7  # 70% of 1ly spacing
    HTML_STAR_CLASS = "mapstar"
    HTML_FLEET_CLASS = "mapfleet"
    HTML_SALVAGE_CLASS = "mapsalvage"
    HTML_ANOMALY_CLASS = "mapanomaly"
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
             }
             .mapanomaly {
                height: 5px;
                width: 5px;
                background-color: #6ff;
                border-radius: 1px;
                position: absolute;
             }"""

    def __init__(self, game, player, dest_mode=False, spectator=False):
        self.game = game
        self.player = player
        self.spectator = bool(spectator)
        self.dest_mode = dest_mode
        self.stars = game.stars.all()
        self._scanner_sources = (
            get_scanner_sources_for_player(game, player)
            if player and not self.spectator else []
        )
        fleets = list(game.fleets.all())
        if player and not self.spectator and not getattr(game, 'no_scanners', False):
            fleets = [
                fleet for fleet in fleets
                if fleet_visible_to_player(fleet, player, sources=self._scanner_sources)
            ]
        self.fleets = fleets
        self.salvages = game.salvages.all()
        self.anomalies = game.anomalys.all()
        self.star_report_tiers = {}
        self.fleet_report_tiers = {}
        self.salvage_report_tiers = {}
        self.star_markers = {}
        self.primary_star_by_position = {}
        self.explored_star_ids = set()
        self.explored_salvage_ids = set()
        if self.spectator:
            self.explored_star_ids = set(self.stars.values_list('id', flat=True))
            self.explored_salvage_ids = set(self.salvages.values_list('id', flat=True))
        elif self.player:
            self.star_markers = dict(
                (
                    star_id,
                    {
                        'type': marker_type,
                        'color': (
                            (
                                PlayerStarMarker.COLOR_BLUE
                                if marker_color == PlayerStarMarker.COLOR_WHITE
                                else marker_color
                            )
                            if marker_color in PlayerStarMarker.COLOR_VALUES
                            else PlayerStarMarker.COLOR_BLUE
                        ),
                    },
                )
                for star_id, marker_type, marker_color in
                PlayerStarMarker.objects.filter(player=self.player).values_list(
                    'star_id',
                    'marker_type',
                    'marker_color',
                )
            )
            reports = list(Report.objects.filter(
                game=self.game,
                player=self.player,
                target_type='star',
            ))
            self.explored_star_ids = set(
                report.target_id for report in reports
            )
            salvage_reports = list(Report.objects.filter(
                game=self.game,
                player=self.player,
                target_type='salvage',
            ))
            self.explored_salvage_ids = set(
                report.target_id for report in salvage_reports
            )
            for report in reports:
                tier = 'advanced'
                try:
                    data = report.get_report_data()
                    tier = data.get('report_tier') or 'advanced'
                except Exception:
                    tier = 'advanced'
                self.star_report_tiers[report.target_id] = tier
            fleet_reports = list(Report.objects.filter(
                game=self.game,
                player=self.player,
                target_type='fleet',
            ))
            for report in fleet_reports:
                tier = 'advanced'
                try:
                    data = report.get_report_data()
                    tier = data.get('report_tier') or 'advanced'
                except Exception:
                    tier = 'advanced'
                self.fleet_report_tiers[report.target_id] = tier
            for report in salvage_reports:
                tier = 'advanced'
                try:
                    data = report.get_report_data()
                    tier = data.get('report_tier') or 'advanced'
                except Exception:
                    tier = 'advanced'
                self.salvage_report_tiers[report.target_id] = tier
            if not getattr(self.game, 'no_scanners', False):
                self.salvages = self.salvages.filter(id__in=self.explored_salvage_ids)
        self.primary_star_by_position = self._build_primary_star_by_position()
        self.map = self.render_map()

    @property
    def width(self):
        """Total map width in pixels including border."""
        # Use game map bounds + border on each side
        return self.game.map_size_x * self.MAP_SCALE + 2 * self.border_offset

    @property
    def height(self):
        """Total map height in pixels including border."""
        # Use game map bounds + border on each side
        return self.game.map_size_y * self.MAP_SCALE + 2 * self.border_offset

    @property
    def border_offset(self):
        """Border offset in pixels."""
        return self.MAP_BORDER * self.MAP_SCALE

    def render_map(self, stars=None, fleets=None, salvages=None, anomalies=None):
        """Render a map of the stars in the game using HTML objects"""
        if stars is None:
            stars = self.stars
        if fleets is None:
            fleets = self.fleets
        if salvages is None:
            salvages = self.salvages
        if anomalies is None:
            anomalies = self.anomalies

        html = ""

        # Track max coordinates for sizing
        self._max_x = 0
        self._max_y = 0

        # Group stars by position to handle multiple at same coordinates
        stars_by_pos = {}
        for star in stars:
            pos = (star.x, star.y)
            if pos not in stars_by_pos:
                stars_by_pos[pos] = []
            stars_by_pos[pos].append(star)
            self._max_x = max(self._max_x, star.x)
            self._max_y = max(self._max_y, star.y)

        for pos, star_group in stars_by_pos.items():
            html += self.render_star_group(star_group)

        for fleet in fleets:
            html += self.render_fleet(fleet)
            self._max_x = max(self._max_x, fleet.x)
            self._max_y = max(self._max_y, fleet.y)

        for salvage in salvages:
            html += self.render_salvage(salvage)
            self._max_x = max(self._max_x, salvage.x)
            self._max_y = max(self._max_y, salvage.y)

        for anomaly in anomalies:
            html += self.render_anomaly(anomaly)
            self._max_x = max(self._max_x, anomaly.x)
            self._max_y = max(self._max_y, anomaly.y)

        return html

    def render_star_group(self, stars):
        """Render stars at the same position with offsets for multiples."""
        html = ""
        anchor_star = self._primary_star_for_group(stars)
        label_star = anchor_star
        if len(stars) == 1:
            html += self.render_star(anchor_star)
            html += self.render_star_name(label_star)
        else:
            # First star at center always represents a real star in the stack.
            html += self.render_star(anchor_star)
            # Additional stars spaced evenly around center (smaller, show individual ownership)
            offset_distance = self.MAP_SCALE * self.MULTI_STAR_OFFSET
            angle_start = 45  # degrees
            satellites = [star for star in stars if star != anchor_star]
            num_satellites = len(satellites)
            angle_step = 360 / num_satellites if num_satellites > 1 else 0
            # Center offset: main star is 5px, satellite is 2px
            # To center satellite around main star's center: (5/2 - 2/2) = 1.5px
            center_adjust = 1.5
            for i, star in enumerate(satellites):
                angle = radians(angle_start + i * angle_step)
                offset_x = center_adjust + offset_distance * cos(angle)
                offset_y = center_adjust + offset_distance * sin(angle)
                html += self.render_star(
                    star,
                    offset_x,
                    offset_y,
                    satellite=True,
                    selection_star=star,
                    primary_star=anchor_star,
                )
            html += self.render_star_name(label_star)
        return html

    def _build_primary_star_by_position(self):
        stars_by_pos = {}
        for star in self.stars:
            pos = (star.x, star.y)
            if pos not in stars_by_pos:
                stars_by_pos[pos] = []
            stars_by_pos[pos].append(star)
        return {
            pos: self._primary_star_for_group(group)
            for pos, group in stars_by_pos.items()
        }

    def _primary_star_for_group(self, stars):
        """Return the canonical primary star for a stacked star location."""
        if not stars:
            return None
        return sorted(
            stars,
            key=self._star_group_priority,
        )[0]

    def _star_group_priority(self, star):
        owner = getattr(star, 'player', None)
        if self.player and owner == self.player:
            owner_priority = 0
        elif owner is not None and self._can_reveal_star_owner(star) and self._is_allied_owner(owner):
            owner_priority = 1
        elif owner is not None and self._can_reveal_star_owner(star):
            owner_priority = 2
        else:
            owner_priority = 3
        homeworld_priority = 0
        if self.player and self.player.homeworld_id == getattr(star, 'id', None):
            homeworld_priority = -1
        return (
            owner_priority,
            homeworld_priority,
            str(getattr(star, 'short_id', '') or ''),
            int(getattr(star, 'id', 0) or 0),
        )

    def render_star_name(self, star):
        """Render a star name label above the star position."""
        # Position using star center (5px marker => +2.5px) for proper text alignment.
        x = star.x * self.MAP_SCALE + self.border_offset + 2.5
        y = star.y * self.MAP_SCALE + self.border_offset + 2.5
        safe_name = escape(star.name or '')
        if self.dest_mode:
            url = (
                f"javascript:submitDestination('{star.short_id}', "
                f"{star.x}, {star.y}, 'star')"
            )
        else:
            url = f"?x={star.x}&y={star.y}&sel={star.short_id}"
        return (
            f'<a href="{url}" class="mapstar-name" '
            f'style="left:{x}px; top:{y}px;" title="{safe_name}">{safe_name}</a>'
        )

    def _is_allied_owner(self, owner):
        if not self.player or not owner:
            return False
        if owner == self.player:
            return False
        from .diplomacy import PERMISSION_SHARE_INTEL, player_grants_permission

        return player_grants_permission(owner, self.player, PERMISSION_SHARE_INTEL)

    def resolve_html_class(self, object):
        """Resolve the HTML class for an object"""

        if isinstance(object, Star):
            html_class = self.HTML_STAR_CLASS
        elif isinstance(object, Fleet):
            html_class = self.HTML_FLEET_CLASS
        elif isinstance(object, Salvage):
            # Salvage is always neutral (no ownership variants)
            return self.HTML_SALVAGE_CLASS
        elif isinstance(object, Anomaly):
            return self.HTML_ANOMALY_CLASS
        else:
            html_class = ""

        if isinstance(object, Star) and not self._can_reveal_star_owner(object):
            class_additional = ""
        elif object.player is None:
            if isinstance(object, Fleet):
                class_additional = "-unowned"
            else:
                class_additional = ""
        elif self.player is not None and object.player == self.player:
            class_additional = "-owned"
        elif self._is_allied_owner(object.player):
            class_additional = "-allied"
        elif object.player is not None:
            class_additional = "-enemy"
        else:
            class_additional = ""

        return f'{html_class}{class_additional}'

    def render_object(
        self,
        object,
        extra_style="",
        offset_x=0,
        offset_y=0,
        class_override=None,
        extra_classes="",
        name_override=None,
        selection_object=None,
        extra_data_attrs="",
    ):
        """Render a game object on map using HTML"""
        selected = selection_object or object
        x = object.x * self.MAP_SCALE + offset_x + self.border_offset
        y = object.y * self.MAP_SCALE + offset_y + self.border_offset
        html_class = class_override or self.resolve_html_class(object)
        if extra_classes:
            html_class = f"{html_class} {extra_classes}"
        name = name_override if name_override is not None else object.name
        style = f"left:{x}px; top:{y}px;{extra_style}"
        if isinstance(selected, Fleet):
            object_type = 'fleet'
        elif isinstance(selected, Salvage):
            object_type = 'salvage'
        elif isinstance(selected, Anomaly):
            object_type = 'anomaly'
        else:
            object_type = 'star'
        data_attrs = (
            f'data-map-object="1" data-object-type="{object_type}" '
            f'data-object-id="{selected.short_id}" data-x="{selected.x}" '
            f'data-y="{selected.y}"'
        )
        if extra_data_attrs:
            data_attrs = f'{data_attrs} {extra_data_attrs}'

        # In destination mode, clicks call JavaScript instead of navigating
        if self.dest_mode and isinstance(object, (Star, Fleet, Salvage, Anomaly)):
            url = (f"javascript:submitDestination('{selected.short_id}', "
                   f"{selected.x}, {selected.y}, '{object_type}')")
        else:
            url = "?x=%i&y=%i&sel=%s" % (selected.x, selected.y, selected.short_id)

        return f'<a href="{url}" title="{name}"><div class="{html_class}" {data_attrs} style="{style}"></div></a>'

    def render_star(
        self,
        star,
        offset_x=0,
        offset_y=0,
        satellite=False,
        class_override=None,
        selection_star=None,
        primary_star=None,
    ):
        """Render a star object on map using HTML"""
        explored_class = self._get_exploration_class(star)
        marker_class = '' if satellite else self._get_star_marker_class(star)
        extra_classes = explored_class
        if marker_class:
            extra_classes = f"{extra_classes} {marker_class}".strip()
        if satellite:
            # Satellite stars use dedicated CSS classes
            satellite_class = self._get_satellite_class(star)
            return self.render_object(
                star,
                extra_style="",
                offset_x=offset_x,
                offset_y=offset_y,
                class_override=satellite_class,
                extra_classes=extra_classes,
                selection_object=selection_star,
                extra_data_attrs=(
                    f'data-primary-object-id="{primary_star.short_id}" '
                    f'data-primary-x="{primary_star.x}" '
                    f'data-primary-y="{primary_star.y}"'
                    if primary_star is not None and primary_star != star else ''
                ),
            )
        else:
            # Main star renders on top
            extra_style = " z-index:2;"
            return self.render_object(
                star,
                extra_style=extra_style,
                offset_x=offset_x,
                offset_y=offset_y,
                class_override=class_override,
                extra_classes=extra_classes,
                selection_object=selection_star,
            )

    def _get_star_marker_class(self, star):
        marker = self.star_markers.get(getattr(star, 'id', None))
        marker_type = marker
        marker_color = PlayerStarMarker.COLOR_BLUE
        if isinstance(marker, dict):
            marker_type = marker.get('type')
            marker_color = marker.get('color') or PlayerStarMarker.COLOR_BLUE
        if marker_color == PlayerStarMarker.COLOR_WHITE:
            marker_color = PlayerStarMarker.COLOR_BLUE
        color_class = 'mapstar-marker-color-%s' % str(marker_color).lower()
        if marker_type == PlayerStarMarker.TYPE_CIRCLE:
            return 'mapstar-marker-circle %s' % color_class
        if marker_type == PlayerStarMarker.TYPE_X:
            return 'mapstar-marker-x %s' % color_class
        return ''

    def _get_exploration_class(self, star):
        """Return star exploration visibility class for current player."""
        if self.spectator:
            return "mapstar-explored"
        if star.player == self.player or star.id in self.explored_star_ids:
            return "mapstar-explored"
        return "mapstar-unexplored"

    def _get_salvage_exploration_class(self, salvage):
        """Return salvage exploration visibility class for current player."""
        if not self.player:
            return "mapstar-explored"
        if salvage.id in self.explored_salvage_ids:
            return "mapstar-explored"
        return "mapstar-unexplored"

    def _can_reveal_star_owner(self, star):
        """Return True if current player can see ownership of the star."""
        if self.spectator:
            return True
        if not self.player:
            return False
        if getattr(self.game, 'no_scanners', False):
            return True
        if star.player == self.player:
            return True
        if self._is_allied_owner(star.player):
            return True
        tier = self.star_report_tiers.get(star.id)
        if tier is None:
            return False
        return tier != 'basic'

    def _get_satellite_class(self, star):
        """Get CSS class for satellite star based on ownership."""
        if self.player is not None and star.player == self.player:
            return "mapstar-satellite-owned"
        elif self._is_allied_owner(star.player):
            return "mapstar-satellite-allied"
        elif star.player is not None and self._can_reveal_star_owner(star):
            return "mapstar-satellite-enemy"
        else:
            return "mapstar-satellite"

    def render_fleet(self, fleet):
        """Render a fleet object on map using HTML with heading rotation"""
        # Base rotation of -135deg makes heading 0 point north
        rotation = -135 + fleet.heading
        extra_style = f" transform: translate(-20%, -20%) rotate({rotation}deg);"
        selection_object = self.primary_star_by_position.get((fleet.x, fleet.y)) or fleet
        return self.render_object(
            fleet,
            extra_style,
            name_override=self._fleet_display_name(fleet),
            selection_object=selection_object,
        )

    def render_salvage(self, salvage):
        """Render a salvage pile on map using HTML (hollow yellow square)"""
        if getattr(salvage, 'salvage_type', None) == Salvage.TYPE_ASTEROID_FIELD:
            return self.render_object(
                salvage,
                class_override="mapsalvage-asteroid",
                extra_classes=self._get_salvage_exploration_class(salvage),
            )
        if getattr(salvage, 'salvage_type', None) == Salvage.TYPE_ANCIENT_DEBRIS:
            return self.render_object(
                salvage,
                class_override="mapsalvage-ancient",
                extra_classes=self._get_salvage_exploration_class(salvage),
                name_override=self._salvage_display_name(salvage),
            )
        return self.render_object(salvage)

    def _fleet_display_name(self, fleet):
        """Return the map tooltip name for a fleet."""
        if self.spectator or not self.player:
            return fleet.name
        if getattr(self.game, 'no_scanners', False):
            return fleet.name
        if fleet.player_id == self.player.id:
            return fleet.name
        if self._is_allied_owner(fleet.player):
            return fleet.name
        tier = self.fleet_report_tiers.get(fleet.id)
        if tier in ('advanced', 'encounter'):
            return fleet.name
        if position_in_scanner_range(
            fleet.x, fleet.y, self._scanner_sources, range_key='advanced'
        ):
            return fleet.name
        return format_basic_unknown_fleet_name(fleet)

    def _salvage_display_name(self, salvage):
        """Return the map tooltip name for a salvage pile."""
        if self.spectator or not self.player:
            return salvage.name
        if getattr(self.game, 'no_scanners', False):
            return salvage.name
        if getattr(salvage, 'salvage_type', None) != Salvage.TYPE_ANCIENT_DEBRIS:
            return salvage.name
        tier = self.salvage_report_tiers.get(salvage.id)
        if tier in ('advanced', 'encounter'):
            return salvage.name
        return format_basic_hidden_salvage_name(salvage)

    def render_anomaly(self, anomaly):
        """Render an anomaly marker on map."""
        anomaly_type = str(getattr(anomaly, 'anomaly_type', '') or '').upper()
        heading = float(getattr(anomaly, 'heading', 0.0) or 0.0)
        render_heading = heading
        if anomaly_type == Anomaly.TYPE_COMET:
            type_class = 'mapanomaly-comet'
            render_heading = heading - 90.0
            # Anchor at comet nucleus center (::before center), not the tail body.
            offset_x, offset_y = (-21, -2)
        elif anomaly_type == Anomaly.TYPE_BLACK_HOLE:
            type_class = 'mapanomaly-blackhole'
            # Match star-sized footprint.
            offset_x, offset_y = (0, 0)
        elif anomaly_type == Anomaly.TYPE_WORMHOLE:
            type_class = 'mapanomaly-wormhole'
            # Match star-sized footprint.
            offset_x, offset_y = (0, 0)
        elif anomaly_type == Anomaly.TYPE_RIFT:
            type_class = 'mapanomaly-rift'
            seed = anomaly.short_id or anomaly.name or str(anomaly.id)
            rift_height = 20 + (sum(ord(ch) for ch in seed) % 31)  # 20..50px
            # Keep the visual center stable as the rift body height varies.
            offset_x = -3
            offset_y = -6 - int(round((rift_height - 20) / 2.0))
            extra_style = (
                " z-index:4; transform: rotate(%.1fdeg); --rift-height:%spx;"
                % (render_heading, rift_height)
            )
            return self.render_object(
                anomaly,
                extra_style=extra_style,
                offset_x=offset_x,
                offset_y=offset_y,
                extra_classes=type_class,
            )
        else:
            type_class = 'mapanomaly-nebula'
            # Center on full nebula silhouette (base + pseudo-elements).
            offset_x, offset_y = (-7, -8)
        nebula_palette_class = ""
        if anomaly_type == Anomaly.TYPE_NEBULA:
            palette = None
            if getattr(anomaly, "thumbnail_path", ""):
                palette = nebula_palette_from_thumbnail(anomaly.thumbnail_path)
            if not palette:
                palettes = ("blue", "orange", "yellow", "red", "white")
                idx = sum(ord(ch) for ch in (anomaly.short_id or anomaly.name or "")) % len(palettes)
                palette = palettes[idx]
            nebula_palette_class = " mapanomaly-nebula-%s" % palette
        return self.render_object(
            anomaly,
            extra_style=" z-index:4; transform: rotate(%.1fdeg);" % render_heading,
            offset_x=offset_x,
            offset_y=offset_y,
            extra_classes="%s%s" % (type_class, nebula_palette_class),
        )
