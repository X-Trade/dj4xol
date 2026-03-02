from math import cos, sin, radians
from html import escape
from .models import Game, Player, Fleet, Star, Salvage, Anomaly, Report

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
        self.fleets = game.fleets.all()
        self.salvages = game.salvages.all()
        self.anomalies = game.anomalys.all()
        self.explored_star_ids = set(
            Report.objects.filter(
                game=self.game,
                player=self.player,
                target_type='star',
            ).values_list('target_id', flat=True)
        )
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
        has_enemy = any(s.player is not None and s.player != self.player for s in stars)

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

        if object.player == self.player:
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

    def _get_satellite_class(self, star):
        """Get CSS class for satellite star based on ownership."""
        if star.player == self.player:
            return "mapstar-satellite-owned"
        elif star.player is not None:
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
        return self.render_object(salvage)

    def render_anomaly(self, anomaly):
        """Render an anomaly marker on map."""
        anomaly_type = str(getattr(anomaly, 'anomaly_type', '') or '').upper()
        inline_fallback = ""
        if anomaly_type == Anomaly.TYPE_COMET:
            type_class = 'mapanomaly-comet'
            inline_fallback = (
                " width:24px; height:10px; position:absolute; background:transparent;"
            )
        elif anomaly_type == Anomaly.TYPE_RIFT:
            type_class = 'mapanomaly-rift'
            inline_fallback = (
                " width:7px; height:20px; position:absolute;"
                " border-radius:76% 24% 78% 22% / 88% 20% 90% 22%;"
                " background:linear-gradient(90deg, rgba(110,64,188,0.48) 0%,"
                " rgba(91,205,255,0.80) 50%, rgba(118,72,196,0.48) 100%);"
            )
        else:
            type_class = 'mapanomaly-nebula'
            inline_fallback = (
                " width:16px; height:16px; position:absolute;"
                " border-radius:43% 57% 52% 48% / 57% 43% 58% 42%;"
                " background:radial-gradient(circle at 42% 35%, rgba(210,245,255,0.65) 0%,"
                " rgba(116,191,255,0.42) 28%, rgba(88,59,172,0.35) 58%, rgba(0,0,0,0) 100%);"
            )
        variant_count = 5 if anomaly_type == Anomaly.TYPE_RIFT else 3
        variant = (sum(ord(ch) for ch in (anomaly.short_id or '')) % variant_count) + 1
        # Per-type visual centering: pseudo-elements make visible extents asymmetrical.
        if anomaly_type == Anomaly.TYPE_RIFT:
            offset_by_variant = {
                1: (-3, -9),
                2: (-4, -11),
                3: (-4, -13),
                4: (-3, -15),
                5: (-4, -12),
            }
        elif anomaly_type == Anomaly.TYPE_COMET:
            # Anchor on nucleus at one end of tail (comet body).
            offset_by_variant = {
                1: (-17, -4),
                2: (-21, -5),
                3: (-25, -6),
            }
        elif anomaly_type == Anomaly.TYPE_NEBULA:
            # Nebula wisps lean upward; nudge down slightly to center on target.
            offset_by_variant = {
                1: (-9, -5),
                2: (-10, -6),
                3: (-10, -7),
            }
        else:
            offset_by_variant = {
                1: (-8, -8),
                2: (-9, -9),
                3: (-10, -10),
            }
        offset_x, offset_y = offset_by_variant.get(variant, (-8, -8))
        variant_style = ""
        if anomaly_type == Anomaly.TYPE_NEBULA:
            if variant == 2:
                variant_style = " width:18px; height:18px;"
            elif variant == 3:
                variant_style = " width:20px; height:20px;"
        nebula_palette_class = ""
        if anomaly_type == Anomaly.TYPE_NEBULA:
            palettes = ("blue", "orange", "yellow", "red", "white")
            idx = sum(ord(ch) for ch in (anomaly.short_id or anomaly.name or "")) % len(palettes)
            nebula_palette_class = " mapanomaly-nebula-%s" % palettes[idx]
        return self.render_object(
            anomaly,
            extra_style=" z-index:4;%s%s" % (inline_fallback, variant_style),
            offset_x=offset_x,
            offset_y=offset_y,
            extra_classes="%s mapanomaly-v%s%s" % (type_class, variant, nebula_palette_class),
        )
