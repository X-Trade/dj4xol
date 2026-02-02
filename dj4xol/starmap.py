from math import cos, sin, radians
from .models import Game, Player, Fleet, Star

class StarMap():
    MAP_SCALE = 6
    MAP_BORDER = 10  # Border in light-years around the map
    MULTI_STAR_OFFSET = 0.7  # 70% of 1ly spacing
    HTML_STAR_CLASS = "mapstar"
    HTML_FLEET_CLASS = "mapfleet"
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
             }"""

    def __init__(self, game, player, dest_mode=False):
        self.game = game
        self.player = player
        self.dest_mode = dest_mode
        self.stars = game.stars.all()
        self.fleets = game.fleets.all()
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

    def render_map(self, stars=None, fleets=None):
        """Render a map of the stars in the game using HTML objects"""
        if stars is None:
            stars = self.stars
        if fleets is None:
            fleets = self.fleets

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

        return html

    def render_star_group(self, stars):
        """Render stars at the same position with offsets for multiples."""
        html = ""
        if len(stars) == 1:
            html += self.render_star(stars[0])
        else:
            # Determine group ownership for main dot color
            group_class = self._resolve_group_class(stars)
            # First star at center (shows group ownership)
            html += self.render_star(stars[0], class_override=group_class)
            # Additional stars spaced evenly around center (smaller, show individual ownership)
            offset_distance = self.MAP_SCALE * self.MULTI_STAR_OFFSET
            angle_start = 45  # degrees
            num_satellites = len(stars) - 1
            angle_step = 360 / num_satellites if num_satellites > 1 else 0
            # Center offset: main star is 5px, satellite is 2px
            # To center satellite around main star's center: (5/2 - 2/2) = 1.5px
            center_adjust = 1.5
            for i, star in enumerate(stars[1:]):
                angle = radians(angle_start + i * angle_step)
                offset_x = center_adjust + offset_distance * cos(angle)
                offset_y = center_adjust + offset_distance * sin(angle)
                html += self.render_star(star, offset_x, offset_y, satellite=True)
        return html

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
        else:
            html_class = ""

        if object.player == self.player:
            class_additional = "-owned"
        elif object.player is not None:
            class_additional = "-enemy"
        else:
            class_additional = ""

        return f'{html_class}{class_additional}'

    def render_object(self, object, extra_style="", offset_x=0, offset_y=0, class_override=None):
        """Render a game object on map using HTML"""
        x = object.x * self.MAP_SCALE + offset_x + self.border_offset
        y = object.y * self.MAP_SCALE + offset_y + self.border_offset
        html_class = class_override or self.resolve_html_class(object)
        name = object.name
        style = f"left:{x}px; top:{y}px;{extra_style}"

        # In destination mode, star clicks call JavaScript instead of navigating
        if self.dest_mode and isinstance(object, Star):
            url = f"javascript:submitDestination('{object.short_id}', {object.x}, {object.y})"
        else:
            url = "?x=%i&y=%i&sel=%s" % (object.x, object.y, object.short_id)

        return f'<a href="{url}" title="{name}"><div class="{html_class}" style="{style}"></div></a>'

    def render_star(self, star, offset_x=0, offset_y=0, satellite=False, class_override=None):
        """Render a star object on map using HTML"""
        if satellite:
            # Satellite stars use dedicated CSS classes
            satellite_class = self._get_satellite_class(star)
            return self.render_object(star, extra_style="", offset_x=offset_x, offset_y=offset_y, class_override=satellite_class)
        else:
            # Main star renders on top
            extra_style = " z-index:2;"
            return self.render_object(star, extra_style=extra_style, offset_x=offset_x, offset_y=offset_y, class_override=class_override)

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