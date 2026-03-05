from math import cos, sin, radians
from html import escape
from .models import Game, Player, Fleet, Star, Salvage, Anomaly, Report
from .anomaly_thumbnails import nebula_palette_from_thumbnail
from .scanners import get_scanner_sources_for_player, fleet_visible_to_player

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

    def __init__(self, game, player, dest_mode=False):
        self.game = game
        self.player = player
        self.dest_mode = dest_mode
        self.stars = game.stars.all()
        self._scanner_sources = get_scanner_sources_for_player(game, player) if player else []
        fleets = list(game.fleets.all())
        if player and not getattr(game, 'no_scanners', False):
            fleets = [
                fleet for fleet in fleets
                if fleet_visible_to_player(fleet, player, sources=self._scanner_sources)
            ]
        self.fleets = fleets
        self.salvages = game.salvages.all()
        self.anomalies = game.anomalys.all()
        self.star_report_tiers = {}
        self.explored_star_ids = set()
        self.explored_salvage_ids = set()
        if self.player:
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
        self.homeworld_star_ids = set(
            game.players.exclude(homeworld=None).values_list('homeworld_id', flat=True)
        )
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
        label_star = next((s for s in stars if s.id in self.homeworld_star_ids), stars[0])
        anchor_star = next(
            (s for s in stars if self._get_exploration_class(s) == "mapstar-explored"),
            stars[0],
        )
        if len(stars) == 1:
            html += self.render_star(anchor_star)
            html += self.render_star_name(label_star)
        else:
            # Determine group ownership for main dot color
            group_class = self._resolve_group_class(stars)
            # First star at center (shows group ownership)
            html += self.render_star(anchor_star, class_override=group_class)
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
                html += self.render_star(star, offset_x, offset_y, satellite=True)
            html += self.render_star_name(label_star)
        return html

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

    def _resolve_group_class(self, stars):
        """Determine CSS class for a group of stars based on ownership mix."""
        has_owned = any(s.player == self.player for s in stars)
        has_enemy = any(
            s.player is not None
            and s.player != self.player
            and self._can_reveal_star_owner(s)
            for s in stars
        )

        if has_owned and has_enemy:
            return "mapstar-mixed"  # Yellow - mix of ours and enemy
        elif has_owned:
            return "mapstar-owned"  # Green - all ours (or ours + unowned)
        elif has_enemy:
            return "mapstar-enemy"  # Red - all enemy (or enemy + unowned)
        else:
            return "mapstar"  # White - all unowned

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
        elif object.player == self.player:
            class_additional = "-owned"
        elif object.player is not None:
            class_additional = "-enemy"
        else:
            class_additional = ""

        return f'{html_class}{class_additional}'

    def render_object(self, object, extra_style="", offset_x=0, offset_y=0, class_override=None, extra_classes=""):
        """Render a game object on map using HTML"""
        x = object.x * self.MAP_SCALE + offset_x + self.border_offset
        y = object.y * self.MAP_SCALE + offset_y + self.border_offset
        html_class = class_override or self.resolve_html_class(object)
        if extra_classes:
            html_class = f"{html_class} {extra_classes}"
        name = object.name
        style = f"left:{x}px; top:{y}px;{extra_style}"
        if isinstance(object, Fleet):
            object_type = 'fleet'
        elif isinstance(object, Salvage):
            object_type = 'salvage'
        elif isinstance(object, Anomaly):
            object_type = 'anomaly'
        else:
            object_type = 'star'
        data_attrs = (
            f'data-map-object="1" data-object-type="{object_type}" '
            f'data-object-id="{object.short_id}" data-x="{object.x}" data-y="{object.y}"'
        )

        # In destination mode, clicks call JavaScript instead of navigating
        if self.dest_mode and isinstance(object, (Star, Fleet, Salvage, Anomaly)):
            url = (f"javascript:submitDestination('{object.short_id}', "
                   f"{object.x}, {object.y}, '{object_type}')")
        else:
            url = "?x=%i&y=%i&sel=%s" % (object.x, object.y, object.short_id)

        return f'<a href="{url}" title="{name}"><div class="{html_class}" {data_attrs} style="{style}"></div></a>'

    def render_star(self, star, offset_x=0, offset_y=0, satellite=False, class_override=None):
        """Render a star object on map using HTML"""
        explored_class = self._get_exploration_class(star)
        if satellite:
            # Satellite stars use dedicated CSS classes
            satellite_class = self._get_satellite_class(star)
            return self.render_object(
                star,
                extra_style="",
                offset_x=offset_x,
                offset_y=offset_y,
                class_override=satellite_class,
                extra_classes=explored_class,
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
                extra_classes=explored_class,
            )

    def _get_exploration_class(self, star):
        """Return star exploration visibility class for current player."""
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
        if not self.player:
            return False
        if getattr(self.game, 'no_scanners', False):
            return True
        if star.player == self.player:
            return True
        tier = self.star_report_tiers.get(star.id)
        if tier is None:
            return False
        return tier != 'basic'

    def _get_satellite_class(self, star):
        """Get CSS class for satellite star based on ownership."""
        if star.player == self.player:
            return "mapstar-satellite-owned"
        elif star.player is not None and self._can_reveal_star_owner(star):
            return "mapstar-satellite-enemy"
        else:
            return "mapstar-satellite"

    def render_fleet(self, fleet):
        """Render a fleet object on map using HTML with heading rotation"""
        # Base rotation of -135deg makes heading 0 point north
        rotation = -135 + fleet.heading
        extra_style = f" transform: translate(-20%, -20%) rotate({rotation}deg);"
        return self.render_object(fleet, extra_style)

    def render_salvage(self, salvage):
        """Render a salvage pile on map using HTML (hollow yellow square)"""
        if getattr(salvage, 'salvage_type', None) == Salvage.TYPE_ASTEROID_FIELD:
            return self.render_object(
                salvage,
                class_override="mapsalvage-asteroid",
                extra_classes=self._get_salvage_exploration_class(salvage),
            )
        return self.render_object(salvage)

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
