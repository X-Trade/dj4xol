from datetime import timedelta
from django.utils import timezone
from dj4xol.starnamer import StarNamer
from .models import (
    Game, Star, Fleet, Player, Account, Anomaly, Salvage,
    random_anomaly_stability_init, random_wormhole_stability_init,
    build_game_short_id, iter_short_id_suffixes,
)
from . import mineral_rules
from .research import get_player_tech_effects
from .fleet_thumbnails import choose_fleet_thumbnail
from .turn import combine_speed_advantages
from .ai_players import AI_MODULE_IDLE, normalize_ai_module_code
from .colony_rules import (
    environment_matches_player_preference,
    habitability_value_for_environment,
)
import random
import math

TURN_INTERVALS = {
    'HOURLY': timedelta(hours=1),
    'DAILY': timedelta(days=1),
    'WEEKLY': timedelta(weeks=1),
}

SECRET_RESOURCE_HOMEWORLD_BUFFER = 25
STARTING_COLONY_RADIUS = 30.0

class GameFactory():
    """A factory class to draft and initialise game instances.
    The factory can create stars and ships, assign players to the game,
    and save the game to the database."""
    def __init__(self, game=None):
        self.starnamer = StarNamer()
        self.stars = []
        self.pending_anomalies = []
        self._spiral_black_holes = []
        self.owner = None
        self.game = game or Game()

    _ROMAN_NUMERALS = [
        'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
        'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI',
    ]

    def new(self):
        """Create a new game instance."""
        self.game = Game()
        self.stars = []
        self.pending_anomalies = []
        self._spiral_black_holes = []
        return self.game
    
    def validate(self):
        """Validate the game instance before saving."""
        if not isinstance(self.game, Game):
            raise TypeError("game is not an instance of the Game model object")
        if self.owner is None:
            raise Exception("game owner not set")
        if not (self.game.map_size_x and self.game.map_size_y):
            raise Exception("map size not set")
        if self.game.map_size_x < 10 or self.game.map_size_y < 10:
            raise Exception("map size too small")
        if len(self.stars) < 1:
            raise Exception("no stars created")
        return True

    def load(self, game):
        """Load an existing game instance into the factory."""
        if not isinstance(game, Game):
            raise TypeError("game is not an instance of the Game model object")
        self.game = game
        self.owner = game.owner
        self.pending_anomalies = []
        self._spiral_black_holes = []
        return self

    def save(self):
        """Save the game and stars to the database.
        Returns the saved game model instance. Use join_player() to add players."""
        self.validate()
        self.game.owner = self.owner
        # Set initial next_generation time for timed turn schemes
        interval = TURN_INTERVALS.get(self.game.turn_scheme)
        if interval:
            self.game.next_generation = timezone.now() + interval
        self._place_secret_resources()
        self.game.save()
        used_short_ids = self._collect_existing_short_ids()
        for star in self.stars:
            star.game = self.game
        self._assign_short_ids(self.stars, used_short_ids)
        Star.objects.bulk_create(self.stars)
        self._create_initial_asteroid_fields(used_short_ids)
        self._create_initial_ancient_debris(used_short_ids)
        if self.pending_anomalies:
            self._assign_short_ids(self.pending_anomalies, used_short_ids)
            Anomaly.objects.bulk_create(self.pending_anomalies)
        self._create_initial_anomalies()
        return self.game

    def _collect_existing_short_ids(self):
        used = set()
        if not self.game or not self.game.pk:
            return used
        models = [Star, Fleet, Salvage, Anomaly]
        for model in models:
            used.update(model.objects.filter(game=self.game).values_list('short_id', flat=True))
        return used

    def _assign_short_ids(self, objects, used_short_ids):
        for obj in objects:
            if obj.short_id:
                used_short_ids.add(obj.short_id)
                continue
            base = build_game_short_id(self.game.short_id, obj.id.int)
            candidate = self._resolve_short_id_collision(base, used_short_ids)
            obj.short_id = candidate
            used_short_ids.add(candidate)

    def _resolve_short_id_collision(self, base, used_short_ids):
        if base not in used_short_ids:
            return base
        for suffix in iter_short_id_suffixes():
            candidate = f"{base[:12 - len(suffix)]}{suffix}"
            if candidate not in used_short_ids:
                return candidate
        return base

    def _create_initial_asteroid_fields(self, used_short_ids):
        """Seed asteroid fields as salvage objects (~10% of star count)."""
        stars = list(self.game.stars.all())
        if not stars:
            return
        count = int(round(len(stars) * 0.10))
        if count <= 0:
            return
        occupied = {(star.x, star.y) for star in stars}
        if self.pending_anomalies:
            occupied.update({(a.x, a.y) for a in self.pending_anomalies})
        existing_salvage = list(Salvage.objects.filter(game=self.game))
        if existing_salvage:
            occupied.update({(s.x, s.y) for s in existing_salvage})
        existing_anomalies = list(Anomaly.objects.filter(game=self.game))
        if existing_anomalies:
            occupied.update({(a.x, a.y) for a in existing_anomalies})
        min_x = 1
        min_y = 1
        max_x = max(1, self.game.map_size_x - 1)
        max_y = max(1, self.game.map_size_y - 1)
        created = []
        attempts = max(100, count * 40)
        while len(created) < count and attempts > 0:
            attempts -= 1
            x = random.randint(min_x, max_x)
            y = random.randint(min_y, max_y)
            if (x, y) in occupied:
                continue
            iron, bor, germ = mineral_rules.random_asteroid_field_minerals()
            salvage = Salvage(
                game=self.game,
                x=x,
                y=y,
                salvage_type=Salvage.TYPE_ASTEROID_FIELD,
                ironium_inventory=iron,
                boranium_inventory=bor,
                germanium_inventory=germ,
            )
            if not salvage.short_id:
                base = build_game_short_id(self.game.short_id, salvage.id.int)
                salvage.short_id = self._resolve_short_id_collision(base, used_short_ids)
                used_short_ids.add(salvage.short_id)
            created.append(salvage)
            occupied.add((x, y))
        if created:
            Salvage.objects.bulk_create(created)

    def _create_initial_ancient_debris(self, used_short_ids):
        """Seed a single ancient debris field if space permits."""
        if Salvage.objects.filter(
            game=self.game, salvage_type=Salvage.TYPE_ANCIENT_DEBRIS
        ).exists():
            return
        stars = list(self.game.stars.all())
        if not stars:
            return
        occupied = {(star.x, star.y) for star in stars}
        if self.pending_anomalies:
            occupied.update({(a.x, a.y) for a in self.pending_anomalies})
        existing_salvage = list(Salvage.objects.filter(game=self.game))
        if existing_salvage:
            occupied.update({(s.x, s.y) for s in existing_salvage})
        existing_anomalies = list(Anomaly.objects.filter(game=self.game))
        if existing_anomalies:
            occupied.update({(a.x, a.y) for a in existing_anomalies})
        min_x = 1
        min_y = 1
        max_x = max(1, self.game.map_size_x - 1)
        max_y = max(1, self.game.map_size_y - 1)
        attempts = 200
        while attempts > 0:
            attempts -= 1
            x = random.randint(min_x, max_x)
            y = random.randint(min_y, max_y)
            if (x, y) in occupied:
                continue
            iron, bor, germ, res_x, res_y, res_z = mineral_rules.random_ancient_debris_minerals()
            salvage = Salvage(
                game=self.game,
                x=x,
                y=y,
                salvage_type=Salvage.TYPE_ANCIENT_DEBRIS,
                ironium_inventory=iron,
                boranium_inventory=bor,
                germanium_inventory=germ,
                resource_x_inventory=res_x,
                resource_y_inventory=res_y,
                resource_z_inventory=res_z,
            )
            if not salvage.short_id:
                base = build_game_short_id(self.game.short_id, salvage.id.int)
                salvage.short_id = self._resolve_short_id_collision(base, used_short_ids)
                used_short_ids.add(salvage.short_id)
            salvage.save()
            break

    def _create_initial_anomalies(self):
        """Seed low-density anomalies for games where anomalies are enabled."""
        if not bool(getattr(self.game, 'anomalies_enabled', False)):
            return
        stars = list(self.game.stars.all())
        if not stars:
            return
        max_count = max(1, int(round(len(stars) * 0.15)))
        count = max(1, int(round(len(stars) * 0.05)))
        count = min(max_count, count)
        occupied = {(star.x, star.y) for star in stars}
        existing_salvage = list(Salvage.objects.filter(game=self.game))
        if existing_salvage:
            occupied.update({(salvage.x, salvage.y) for salvage in existing_salvage})
        existing_anomalies = list(Anomaly.objects.filter(game=self.game))
        if existing_anomalies:
            occupied.update({(anomaly.x, anomaly.y) for anomaly in existing_anomalies})
        created = []
        existing_count = len(existing_anomalies)
        type_names = {
            Anomaly.TYPE_NEBULA: 'Nebula',
            Anomaly.TYPE_COMET: 'Comet',
            Anomaly.TYPE_RIFT: 'Rift',
            Anomaly.TYPE_BLACK_HOLE: 'Black Hole',
            Anomaly.TYPE_WORMHOLE: 'Wormhole',
        }
        min_x = 1
        min_y = 1
        max_x = max(1, self.game.map_size_x - 1)
        max_y = max(1, self.game.map_size_y - 1)
        attempts = max(100, count * 40)
        while len(created) < count and attempts > 0:
            attempts -= 1
            anomaly_type = random.choice([
                Anomaly.TYPE_NEBULA,
                Anomaly.TYPE_COMET,
                Anomaly.TYPE_RIFT,
                Anomaly.TYPE_BLACK_HOLE,
                Anomaly.TYPE_WORMHOLE,
            ])
            if anomaly_type == Anomaly.TYPE_WORMHOLE:
                if len(created) + 2 > count:
                    continue
                x1 = y1 = x2 = y2 = None
                for _ in range(80):
                    tx = random.randint(min_x, max_x)
                    ty = random.randint(min_y, max_y)
                    if (tx, ty) in occupied:
                        continue
                    x1, y1 = tx, ty
                    break
                if x1 is None:
                    continue
                for _ in range(80):
                    tx = random.randint(min_x, max_x)
                    ty = random.randint(min_y, max_y)
                    if (tx, ty) in occupied or (tx, ty) == (x1, y1):
                        continue
                    x2, y2 = tx, ty
                    break
                if x2 is None:
                    continue
                ordinal = existing_count + len(created) + 1
                pair_name = '%s %s' % (type_names.get(anomaly_type, 'Anomaly'), ordinal)
                pair_name_b = '%s %s' % (type_names.get(anomaly_type, 'Anomaly'), ordinal + 1)
                wormhole_a = Anomaly(
                    game=self.game,
                    x=x1,
                    y=y1,
                    anomaly_type=Anomaly.TYPE_WORMHOLE,
                    name=pair_name,
                    heading=random.random() * 360.0,
                    stability=random_wormhole_stability_init(),
                )
                wormhole_b = Anomaly(
                    game=self.game,
                    x=x2,
                    y=y2,
                    anomaly_type=Anomaly.TYPE_WORMHOLE,
                    name=pair_name_b,
                    heading=random.random() * 360.0,
                    stability=random_wormhole_stability_init(),
                )
                created.extend([wormhole_a, wormhole_b])
                occupied.add((x1, y1))
                occupied.add((x2, y2))
                continue

            x = random.randint(min_x, max_x)
            y = random.randint(min_y, max_y)
            key = (x, y)
            if key in occupied:
                continue
            ordinal = existing_count + len(created) + 1
            created.append(Anomaly(
                game=self.game,
                x=x,
                y=y,
                anomaly_type=anomaly_type,
                name='%s %s' % (type_names.get(anomaly_type, 'Anomaly'), ordinal),
                heading=random.random() * 360.0,
                stability=random_anomaly_stability_init(),
            ))
            occupied.add(key)
        if created:
            used_short_ids = self._collect_existing_short_ids()
            self._assign_short_ids(created, used_short_ids)
            Anomaly.objects.bulk_create(created)
            wormholes = list(Anomaly.objects.filter(
                game=self.game,
                anomaly_type=Anomaly.TYPE_WORMHOLE,
                wormhole_pair__isnull=True,
            ).order_by('id'))
            for idx in range(0, len(wormholes), 2):
                if idx + 1 >= len(wormholes):
                    break
                a = wormholes[idx]
                b = wormholes[idx + 1]
                a.wormhole_pair = b
                b.wormhole_pair = a
                a.save(update_fields=['wormhole_pair'])
                b.save(update_fields=['wormhole_pair'])
    
    def set_year(self, year):
        self.game.year = year
        return self

    def set_owner(self, account):
        """Set the owner of the game (the Account that created it)."""
        if not isinstance(account, Account):
            raise TypeError("owner is not an instance of the Account model object")
        self.owner = account
        return self

    def set_map_size(self, x, y):
        self.game.map_size_x = x
        self.game.map_size_y = y
        return self

    def create_stars(self, stars, clusters=False, spiral_arms=False, systems=False, improved_names=False):
        if not (self.game.map_size_x or self.game.map_size_y):
            raise Exception("cannot add stars to game until map size is set")
        if spiral_arms:
            self._create_spiral_arm_galaxy(stars)
        elif clusters:
            self._create_star_clusters(stars)
        else:
            self._create_random_stars(stars)
        if systems:
            self._add_systems()
        if systems and improved_names:
            self._apply_improved_star_names(clusters=clusters)
        return self

    def _roman_numeral(self, index):
        if index <= 0:
            return 'I'
        if index <= len(self._ROMAN_NUMERALS):
            return self._ROMAN_NUMERALS[index - 1]
        return str(index)

    def _find_system_clusters(self, coords, clusters=False):
        coords = list(coords)
        if not coords:
            return []
        if clusters:
            link_distance = 30.0
        else:
            link_distance = 16.0
        remaining = set(coords)
        groups = []
        while remaining:
            start = remaining.pop()
            component = {start}
            frontier = [start]
            while frontier:
                current = frontier.pop()
                neighbors = [
                    other for other in list(remaining)
                    if math.sqrt((current[0] - other[0]) ** 2 + (current[1] - other[1]) ** 2) <= link_distance
                ]
                for other in neighbors:
                    remaining.remove(other)
                    component.add(other)
                    frontier.append(other)
            if len(component) >= 2:
                groups.append(component)
        return groups

    def _ordered_coord_stars(self, stars):
        return sorted(
            stars,
            key=lambda star: (
                str(getattr(star, 'short_id', '') or ''),
                str(getattr(star, 'name', '') or ''),
            ),
        )

    def _coord_anchor_name(self, stars):
        ordered = self._ordered_coord_stars(stars)
        if not ordered:
            return ''
        return str(getattr(ordered[0], 'name', '') or '').strip()

    def _coord_uses_related_name(self, stars):
        anchor_name = self._coord_anchor_name(stars)
        if not self.starnamer.is_traditional_name(anchor_name):
            return False
        return random.random() >= 0.25

    def _cluster_root_name(self, coords, stars_by_coord, used_roots):
        for coord in sorted(coords):
            anchor_name = self._coord_anchor_name(stars_by_coord.get(coord, []))
            if (
                self.starnamer.is_traditional_name(anchor_name) and
                ' ' not in anchor_name and
                anchor_name not in used_roots
            ):
                used_roots.add(anchor_name)
                return anchor_name
        root = self.starnamer.get_unique_root(used_roots=used_roots)
        used_roots.add(root)
        return root

    def _apply_improved_star_names(self, clusters=False):
        stars_by_coord = {}
        for star in self.stars:
            stars_by_coord.setdefault((star.x, star.y), []).append(star)
        related_coords = {
            coord for coord, stars in stars_by_coord.items()
            if self._coord_uses_related_name(stars)
        }
        cluster_groups = self._find_system_clusters(related_coords, clusters=clusters)
        used_roots = set()
        assignments = {}

        for coord_group in cluster_groups:
            ordered_coords = sorted(coord_group)
            if len(ordered_coords) < 2:
                continue
            root = self._cluster_root_name(ordered_coords, stars_by_coord, used_roots)
            for idx, coord in enumerate(ordered_coords):
                if idx < len(self.starnamer.cluster_prefixes):
                    assignments[coord] = '%s %s' % (self.starnamer.cluster_prefixes[idx], root)
                else:
                    assignments[coord] = '%s %s' % (root, idx + 1)

        for coord, stars in stars_by_coord.items():
            ordered_stars = self._ordered_coord_stars(stars)
            if coord in assignments:
                base_name = assignments[coord]
            elif len(ordered_stars) > 1 and coord in related_coords:
                base_name = self._coord_anchor_name(ordered_stars)
            else:
                continue
            if len(ordered_stars) == 1:
                ordered_stars[0].name = base_name
                continue
            for idx, star in enumerate(ordered_stars, start=1):
                star.name = '%s %s' % (base_name, self._roman_numeral(idx))

    def _reserve_spiral_black_holes(self, center_x, center_y, total_stars):
        if not bool(getattr(self.game, 'anomalies_enabled', False)):
            return
        if total_stars >= 200:
            count = random.choice([1, 2, 3])
        elif total_stars >= 100:
            count = random.choice([1, 2])
        else:
            count = 1
        occupied = set(self._spiral_black_holes)
        candidates = []
        for _ in range(count):
            placed = False
            for _ in range(120):
                radius = random.random() * 7.0
                angle = random.random() * 2.0 * math.pi
                x = int(round(center_x + math.cos(angle) * radius))
                y = int(round(center_y + math.sin(angle) * radius))
                x = max(1, min(self.game.map_size_x - 1, x))
                y = max(1, min(self.game.map_size_y - 1, y))
                key = (x, y)
                if key in occupied:
                    continue
                candidates.append(key)
                occupied.add(key)
                placed = True
                break
            if not placed:
                break
        if not candidates:
            return
        central = min(
            candidates,
            key=lambda pos: (pos[0] - center_x) ** 2 + (pos[1] - center_y) ** 2
        )
        for x, y in candidates:
            stability = 100 if (x, y) == central else random.randint(60, 90)
            ordinal = len(self.pending_anomalies) + 1
            self.pending_anomalies.append(Anomaly(
                game=self.game,
                x=x,
                y=y,
                anomaly_type=Anomaly.TYPE_BLACK_HOLE,
                name='Black Hole %s' % ordinal,
                heading=random.random() * 360.0,
                stability=stability,
            ))
            self._spiral_black_holes.append((x, y))

    def _is_near_black_hole(self, x, y, min_distance=3.0):
        if not self._spiral_black_holes:
            return False
        min_sq = float(min_distance) ** 2
        for bx, by in self._spiral_black_holes:
            dx = float(x - bx)
            dy = float(y - by)
            if (dx * dx + dy * dy) < min_sq:
                return True
        return False

    def _create_spiral_arm_galaxy(self, stars):
        min_x = 1
        min_y = 1
        max_x = self.game.map_size_x - 1
        max_y = self.game.map_size_y - 1
        center_x = self.game.map_size_x / 2.0
        center_y = self.game.map_size_y / 2.0
        max_radius = (min(self.game.map_size_x, self.game.map_size_y) / 2.0) - 2.0
        max_radius = max(10.0, max_radius)

        total = max(1, int(stars))
        self._reserve_spiral_black_holes(center_x, center_y, total)
        edge_count = max(1, int(round(total * 0.05)))
        core_count = max(1, int(round(total * 0.18)))
        arm_count = max(0, total - edge_count - core_count)

        inner_gap = max(3.0, min(7.0, max_radius * 0.08))
        core_radius = max(inner_gap + 2.0, max_radius * 0.22)
        arm_inner = max(core_radius * 0.85, inner_gap + 2.0)
        edge_min = max_radius * 0.70

        def clamp_point(x, y):
            return (
                max(min_x, min(max_x, int(round(x)))),
                max(min_y, min(max_y, int(round(y)))),
            )

        occupied = set()

        def add_star(x, y):
            x, y = clamp_point(x, y)
            if self._is_near_black_hole(x, y, min_distance=3.0):
                return False
            if (x, y) in occupied:
                return False
            name = self.starnamer.get_unique()
            self.stars.append(Star(name=name, x=x, y=y))
            occupied.add((x, y))
            return True

        def place_with_attempts(generator, attempts=80):
            for _ in range(attempts):
                x, y = generator()
                if add_star(x, y):
                    return True
            # Fallback: random placement away from black holes.
            for _ in range(120):
                x = random.randint(min_x, max_x)
                y = random.randint(min_y, max_y)
                if add_star(x, y):
                    return True
            return False

        arms = random.choice([2, 3, 4])
        arm_twists = 2.4
        arm_offsets = [2.0 * math.pi * i / float(arms) for i in range(arms)]
        arm_width = max(1.5, max_radius * 0.02)

        for _ in range(arm_count):
            arm_idx = random.randrange(arms)
            base_angle = arm_offsets[arm_idx]

            def arm_generator():
                radial = arm_inner + (max_radius - arm_inner) * (random.random() ** 0.75)
                theta = base_angle + (radial / max_radius) * (arm_twists * 2.0 * math.pi)
                radial += random.gauss(0.0, arm_width)
                theta += random.gauss(0.0, 0.18)
                x = center_x + math.cos(theta) * radial
                y = center_y + math.sin(theta) * radial
                return x, y

            place_with_attempts(arm_generator)

        for _ in range(core_count):
            def core_generator():
                radial = inner_gap + (core_radius - inner_gap) * (random.random() ** 2.0)
                theta = random.random() * 2.0 * math.pi
                radial += random.gauss(0.0, 1.0)
                x = center_x + math.cos(theta) * radial
                y = center_y + math.sin(theta) * radial
                return x, y

            place_with_attempts(core_generator)

        for _ in range(edge_count):
            def edge_generator():
                radial = edge_min + (max_radius - edge_min) * (random.random() ** 0.5)
                theta = random.random() * 2.0 * math.pi
                x = center_x + math.cos(theta) * radial
                y = center_y + math.sin(theta) * radial
                return x, y

            place_with_attempts(edge_generator)

    def _create_random_stars(self, stars):
        """Create stars randomly in the game."""
        min_x = 1
        min_y = 1
        max_x = self.game.map_size_x - 1
        max_y = self.game.map_size_y - 1
        occupied = set()
        for _ in range(stars):
            x = None
            y = None
            for _ in range(200):
                cand_x = random.randint(min_x, max_x)
                cand_y = random.randint(min_y, max_y)
                if (cand_x, cand_y) not in occupied:
                    x = cand_x
                    y = cand_y
                    break
            if x is None or y is None:
                found = False
                for cand_x in range(min_x, max_x + 1):
                    for cand_y in range(min_y, max_y + 1):
                        if (cand_x, cand_y) not in occupied:
                            x = cand_x
                            y = cand_y
                            found = True
                            break
                    if found:
                        break
            if x is None or y is None:
                break
            name = self.starnamer.get_unique()
            self.stars.append(Star(name=name, x=x, y=y))
            occupied.add((x, y))
        return self

    def _create_star_clusters(self, stars, system_size=6, cluster_radius=25, min_cluster_distance=40):
        """Create stars in clusters with better spacing."""
        min_x = 1
        min_y = 1
        max_x = self.game.map_size_x - 1
        max_y = self.game.map_size_y - 1
        
        cluster_centers = []
        occupied = set()
        created = 0
        
        while created < stars:
            # Find a cluster center that's far enough from existing clusters
            attempts = 0
            while attempts < 50:  # Prevent infinite loop
                cluster_x = random.randint(min_x + cluster_radius, max_x - cluster_radius)
                cluster_y = random.randint(min_y + cluster_radius, max_y - cluster_radius)
                
                # Check if this cluster center is far enough from existing ones
                too_close = False
                for cx, cy in cluster_centers:
                    distance = ((cluster_x - cx) ** 2 + (cluster_y - cy) ** 2) ** 0.5
                    if distance < min_cluster_distance:
                        too_close = True
                        break
                
                if not too_close:
                    break
                attempts += 1
            
            # If we couldn't find a good spot after many attempts, just use the last attempt
            cluster_centers.append((cluster_x, cluster_y))
            
            # Create stars in this cluster with more spread
            stars_in_cluster = min(system_size, stars - created)
            for _ in range(stars_in_cluster):
                name = self.starnamer.get_unique()
                # Use larger, more varied offsets for better spread
                x = None
                y = None
                for _ in range(80):
                    angle = random.random() * 2 * math.pi  # Random angle
                    radius = random.random() * cluster_radius  # Random distance from center
                    ofs_x = int(radius * math.cos(angle))
                    ofs_y = int(radius * math.sin(angle))
                    cand_x = max(min_x, min(max_x, cluster_x + ofs_x))
                    cand_y = max(min_y, min(max_y, cluster_y + ofs_y))
                    if (cand_x, cand_y) not in occupied:
                        x = cand_x
                        y = cand_y
                        break
                if x is None or y is None:
                    for _ in range(200):
                        cand_x = random.randint(min_x, max_x)
                        cand_y = random.randint(min_y, max_y)
                        if (cand_x, cand_y) not in occupied:
                            x = cand_x
                            y = cand_y
                            break
                if x is None or y is None:
                    break
                self.stars.append(Star(name=name, x=x, y=y))
                occupied.add((x, y))
                created += 1
                
                if created >= stars:
                    break
        
        return self

    def _add_systems(self):
        """Add 1-5 companion stars to 25% of existing stars at the same coordinates.

        Uses squared distribution so 1 companion is most common, 5 is rare.
        """
        num_systems = len(self.stars) // 4  # 25% of stars become systems
        system_stars = random.sample(self.stars, num_systems)
        for star in system_stars:
            # Squared distribution: bias towards lower numbers
            # random()**2 gives 0-1 biased towards 0, scale to 1-5
            companions = int(1 + 4 * (random.random() ** 2))
            for _ in range(companions):
                name = self.starnamer.get_unique()
                self.stars.append(Star(name=name, x=star.x, y=star.y))
        return self
    
    def _distance(self, star1, star2):
        """Calculate distance between two stars."""
        return math.sqrt((star1.x - star2.x) ** 2 + (star1.y - star2.y) ** 2)

    def _star_has_secret_resources(self, star):
        return any(
            int(getattr(star, f'{key}_yield', 0) or 0) > 0 or
            int(getattr(star, f'{key}_inventory', 0) or 0) > 0
            for key in mineral_rules.SECRET_RESOURCE_KEYS
        )

    def _is_large_map(self):
        return (
            int(self.game.map_size_x or 0) > 200 and
            int(self.game.map_size_y or 0) > 200 and
            len(self.stars) > 150
        )

    def _pick_secret_resource_star(self, occupied_positions):
        candidates = [
            star for star in self.stars
            if not self._star_has_secret_resources(star)
            and star.player is None
            and (star.x, star.y) not in occupied_positions
        ]
        if not candidates:
            return None

        homeworlds = [p.homeworld for p in self.game.players.select_related('homeworld') if p.homeworld]
        if not homeworlds:
            return random.choice(candidates)

        min_dist = self._min_homeworld_distance()
        far_candidates = [
            star for star in candidates
            if all(self._distance(star, hw) >= min_dist for hw in homeworlds)
        ]
        if far_candidates:
            return random.choice(far_candidates)

        return max(
            candidates,
            key=lambda s: min(self._distance(s, hw) for hw in homeworlds),
        )

    def _place_secret_resources(self):
        if not self.stars:
            return
        occupied_positions = set()
        for star in self.stars:
            if self._star_has_secret_resources(star):
                occupied_positions.add((star.x, star.y))

        for key in mineral_rules.SECRET_RESOURCE_KEYS:
            placements = 1
            if self._is_large_map() and random.random() < 0.30:
                placements = 2
            for _ in range(placements):
                star = self._pick_secret_resource_star(occupied_positions)
                if not star:
                    break
                setattr(star, f'{key}_yield', random.randint(50, 100))
                setattr(star, f'{key}_inventory', mineral_rules.random_surface_germanium_init())
                occupied_positions.add((star.x, star.y))

    def _min_homeworld_distance(self):
        """Minimum distance between homeworlds: 250ly or 25% of shortest dimension."""
        return min(250, min(self.game.map_size_x, self.game.map_size_y) * 0.25)

    def _game_has_systems(self):
        stars = list(self.game.stars.all()) if self.game.pk else list(self.stars)
        seen = set()
        for star in stars:
            coord = (int(star.x), int(star.y))
            if coord in seen:
                return True
            seen.add(coord)
        return False

    def _split_starting_colonists(self, player, colony_count):
        total = max(0, int(player.starting_colonists or 20)) * 1000
        count = max(1, int(colony_count or 1))
        base = total // count
        remainder = total % count
        return [base + (1 if idx < remainder else 0) for idx in range(count)]

    def _split_starting_integer(self, total, colony_count):
        total = max(0, int(total or 0))
        count = max(1, int(colony_count or 1))
        base = total // count
        remainder = total % count
        return [base + (1 if idx < remainder else 0) for idx in range(count)]

    def _star_habitability_score_for_player(self, player, star):
        proportions = []
        for env in ['gravity', 'temperature', 'radiation']:
            proportions.append(max(
                0.0,
                habitability_value_for_environment(player, env, getattr(star, env)),
            ))
        return sum(proportions) / 3.0

    def _is_perfect_for_player(self, player, star):
        return all(
            environment_matches_player_preference(player, env, getattr(star, env))
            for env in ['gravity', 'temperature', 'radiation']
        )

    def _find_secondary_starting_colony_candidates(self, player, homeworld, available_stars):
        candidates = [
            star for star in available_stars
            if star.id != homeworld.id and self._distance(star, homeworld) <= STARTING_COLONY_RADIUS
        ]
        if not candidates:
            return []
        non_stacked = [
            star for star in candidates
            if (int(star.x), int(star.y)) != (int(homeworld.x), int(homeworld.y))
        ]
        if non_stacked:
            candidates = non_stacked
        less_habitable = [
            star for star in candidates if not self._is_perfect_for_player(player, star)
        ]
        if less_habitable:
            candidates = less_habitable
        return sorted(
            candidates,
            key=lambda star: (
                -self._star_habitability_score_for_player(player, star),
                self._distance(star, homeworld),
                int(star.id.int),
            ),
        )

    def _secondary_colony_env_value(self, player, env):
        center = float(getattr(player, '%s_center' % env))
        minimum = float(player.hab_min(env))
        maximum = float(player.hab_max(env))
        width = max(0.0, maximum - minimum)
        preferred_step = max(0.05, min(0.25, width / 4.0 if width > 0 else 0.05))
        candidates = [center + preferred_step, center - preferred_step]
        for value in candidates:
            if minimum <= value <= maximum and abs(value - center) > 1e-9:
                return value
        fallback = center + 0.05 if center <= 1.95 else center - 0.05
        return max(0.0, min(2.0, fallback))

    def _create_secondary_starting_colony_star(self, player, homeworld):
        occupied = {
            (int(star.x), int(star.y))
            for star in self.game.stars.all()
        }
        x = y = None
        for _ in range(200):
            dx = random.randint(-int(STARTING_COLONY_RADIUS), int(STARTING_COLONY_RADIUS))
            dy = random.randint(-int(STARTING_COLONY_RADIUS), int(STARTING_COLONY_RADIUS))
            if dx == 0 and dy == 0:
                continue
            if (dx * dx) + (dy * dy) > (STARTING_COLONY_RADIUS * STARTING_COLONY_RADIUS):
                continue
            candidate_x = max(0, min(int(self.game.map_size_x), int(homeworld.x) + dx))
            candidate_y = max(0, min(int(self.game.map_size_y), int(homeworld.y) + dy))
            if (candidate_x, candidate_y) in occupied:
                continue
            x = candidate_x
            y = candidate_y
            break
        if x is None or y is None:
            x = int(homeworld.x)
            y = int(homeworld.y)

        star = Star(
            game=self.game,
            name=self.starnamer.get_unique(),
            x=x,
            y=y,
            gravity=self._secondary_colony_env_value(player, 'gravity'),
            temperature=self._secondary_colony_env_value(player, 'temperature'),
            radiation=self._secondary_colony_env_value(player, 'radiation'),
        )
        used_short_ids = self._collect_existing_short_ids()
        self._assign_short_ids([star], used_short_ids)
        star.save()
        return star

    def _assign_starting_colony_to_player(
        self,
        player,
        star,
        colonists,
        mines=0,
        factories=0,
        is_homeworld=False,
    ):
        star.player = player
        star.colonists = max(0, int(colonists or 0))
        star.mines = max(0, int(mines or 0))
        star.factories = max(0, int(factories or 0))
        if is_homeworld:
            # Set environmentals to player's ideal (center) values
            star.gravity = player.gravity_center
            star.temperature = player.temperature_center
            star.radiation = player.radiation_center
            # Transpose homeworld yields from 0-100 into 50-100.
            star.ironium_yield = int(star.ironium_yield / 2.0 + 50)
            star.boranium_yield = int(star.boranium_yield / 2.0 + 50)
            star.germanium_yield = int(star.germanium_yield / 2.0 + 50)
            # Apply remaining starting infrastructure
            star.labs = max(0, int(player.starting_labs or 0))
            star.shipyards = max(0, int(player.starting_shipyards or 0))
            # Ensure homeworld has minimum surface minerals (1000kt each)
            star.ironium_inventory = max(1000, star.ironium_inventory)
            star.boranium_inventory = max(1000, star.boranium_inventory)
            star.germanium_inventory = max(1000, star.germanium_inventory)
            # Apply leftover points to surface minerals (10kt per point) unless routed to research.
            if (player.leftover_points and player.leftover_points > 0 and
                    not player.spend_leftover_points_on_research):
                total_kt = int(player.leftover_points * 10)
                if total_kt > 0:
                    weights = [
                        max(1, star.ironium_yield),
                        max(1, star.boranium_yield),
                        max(1, star.germanium_yield),
                    ]
                    total_weight = sum(weights)
                    base_alloc = [
                        int(total_kt * weights[0] / total_weight),
                        int(total_kt * weights[1] / total_weight),
                        int(total_kt * weights[2] / total_weight),
                    ]
                    remainder = total_kt - sum(base_alloc)
                    for _ in range(remainder):
                        pick = random.choices([0, 1, 2], weights=weights, k=1)[0]
                        base_alloc[pick] += 1
                    star.ironium_inventory += base_alloc[0]
                    star.boranium_inventory += base_alloc[1]
                    star.germanium_inventory += base_alloc[2]
            # Override star name if player has a homeworld name set
            if player.homeworld_name:
                star.name = player.homeworld_name
        star.save()
        if is_homeworld:
            player.homeworld = star
            player.save(update_fields=['homeworld'])
        return star

    def _find_homeworld_star(self, available_stars):
        """Find a suitable star for a homeworld, respecting minimum distance from others."""
        if self.game.pk:
            from django.db.models import Q
            secret_filter = Q()
            for key in mineral_rules.SECRET_RESOURCE_KEYS:
                secret_filter |= Q(**{f'{key}_yield__gt': 0})
                secret_filter |= Q(**{f'{key}_inventory__gt': 0})
            secret_stars = list(self.game.stars.filter(secret_filter))
        else:
            secret_stars = [
                star for star in self.stars if self._star_has_secret_resources(star)
            ]

        def near_secret(star):
            for secret in secret_stars:
                if self._distance(star, secret) < SECRET_RESOURCE_HOMEWORLD_BUFFER:
                    return True
            return False

        non_secret = [s for s in available_stars if not self._star_has_secret_resources(s)]
        candidates = non_secret or list(available_stars)
        preferred = [s for s in candidates if not near_secret(s)]
        if preferred:
            candidates = preferred

        existing_homeworlds = [p.homeworld for p in self.game.players.select_related('homeworld')
                              if p.homeworld]
        if not existing_homeworlds:
            return random.choice(candidates)

        min_dist = self._min_homeworld_distance()

        # Find stars far enough from all existing homeworlds
        suitable = [s for s in candidates
                    if all(self._distance(s, hw) >= min_dist for hw in existing_homeworlds)]

        if suitable:
            return random.choice(suitable)

        # Fallback: pick the star with maximum distance to nearest homeworld
        return max(candidates, key=lambda s: min(self._distance(s, hw) for hw in existing_homeworlds))

    def _assign_homeworld_to_player(self, player, star):
        """Assign a specific star as homeworld to a player with starting population.
        Sets star environmentals to player's habitable centers and optionally renames.
        Transposes resource yields from 0-100% into 50-100%, and ensures
        surface minerals are at least 1000kt."""
        self._assign_starting_colony_to_player(
            player,
            star,
            int(player.starting_colonists or 20) * 1000,
            is_homeworld=True,
        )
        return player

    def _resolve_starting_tech_level(self, race):
        requested_level = max(0, int(getattr(race, 'starting_tech_level', 0) or 0))
        max_allowed = max(0, int(getattr(self.game, 'max_starting_tech_level', 0) or 0))
        effective_level = min(requested_level, max_allowed)

        from .research import get_starting_tech_balance_cost
        requested_cost = float(get_starting_tech_balance_cost(requested_level))
        effective_cost = float(get_starting_tech_balance_cost(effective_level))
        refunded_points = max(0.0, requested_cost - effective_cost)
        return effective_level, refunded_points

    def _apply_starting_research_level(self, player):
        from .research import ensure_player_research_rows
        start_level = max(0, int(getattr(player, 'starting_tech_level', 0) or 0))
        rows = ensure_player_research_rows(player)
        for row in rows:
            row.current_level = float(start_level)
            row.stored_rp = 0.0
            row.save(update_fields=['current_level', 'stored_rp'])

    def join_player(self, account, race, invited=False, is_ai=False, ai_module=''):
        """Add a player to an existing game with homeworld assignment.
        Returns the created Player instance or None if joining failed.
        Game owner and invited players can join non-joinable games."""
        if account is None and not bool(is_ai):
            return None

        is_owner = (account is not None and account == self.game.owner)
        can_bypass = is_owner or invited

        if not can_bypass:
            if not self.game.joinable:
                return None
            human_player_count = self.game.players.filter(is_ai=False).count()
            if self.game.max_players and human_player_count >= self.game.max_players:
                return None

        if account is not None and self.game.players.filter(account=account).exists():
            return None

        available_stars = list(self.game.stars.filter(player=None))
        if not available_stars:
            return None

        ai_module_code = ''
        if bool(is_ai):
            ai_module_code = normalize_ai_module_code(ai_module) or AI_MODULE_IDLE

        player = Player(
            game=self.game,
            account=account,
            name=race.name,
            plural_name=race.plural_name,
            homeworld_name=race.homeworld_name,
            race_type=race.race_type,
            is_ai=bool(is_ai),
            ai_module=ai_module_code,
            ai_last_checkin_year=(int(self.game.year or 0) if bool(is_ai) else None),
        )
        player.starting_colonists = race.starting_colonists
        player.starting_mines = race.starting_mines
        player.starting_factories = race.starting_factories
        player.starting_labs = race.starting_labs
        player.starting_shipyards = race.starting_shipyards
        player.starting_fleets = race.starting_fleets
        effective_starting_tech_level, refunded_points = self._resolve_starting_tech_level(race)
        player.starting_tech_level = effective_starting_tech_level
        player.convert_unused_buildpoints_to_research = (
            race.convert_unused_buildpoints_to_research
        )
        player.singular_research = race.singular_research
        player.fixed_homeworld = bool(getattr(race, 'fixed_homeworld', False))
        player.spend_leftover_points_on_research = race.spend_leftover_points_on_research
        player.leftover_points = float(race.leftover_points or 0.0) + float(refunded_points)
        player.copy_habitability_from(race)
        player.save()
        starting_colony_count = max(
            1,
            int(getattr(race.race_type, 'starting_colonies', 1) or 1),
        )
        colonist_allocations = self._split_starting_colonists(player, starting_colony_count)
        mine_allocations = self._split_starting_integer(player.starting_mines, starting_colony_count)
        factory_allocations = self._split_starting_integer(player.starting_factories, starting_colony_count)
        homeworld = self._find_homeworld_star(available_stars)
        self._assign_starting_colony_to_player(
            player,
            homeworld,
            colonist_allocations[0],
            mines=mine_allocations[0],
            factories=factory_allocations[0],
            is_homeworld=True,
        )
        remaining = max(0, starting_colony_count - 1)
        if remaining:
            available_secondary = list(self.game.stars.filter(player=None))
            secondary_candidates = self._find_secondary_starting_colony_candidates(
                player,
                homeworld,
                available_secondary,
            )
            secondary_stars = list(secondary_candidates[:remaining])
            while len(secondary_stars) < remaining:
                created_star = self._create_secondary_starting_colony_star(player, homeworld)
                secondary_stars.append(created_star)
            for idx, (star, colonists) in enumerate(zip(secondary_stars, colonist_allocations[1:]), start=1):
                self._assign_starting_colony_to_player(
                    player,
                    star,
                    colonists,
                    mines=mine_allocations[idx],
                    factories=factory_allocations[idx],
                    is_homeworld=False,
                )
        self._apply_starting_research_level(player)
        self._create_starting_fleets(player)
        if (not bool(is_ai)) and self.game.max_players and self.game.joinable:
            human_player_count = self.game.players.filter(is_ai=False).count()
            if human_player_count >= int(self.game.max_players):
                self.game.joinable = False
                self.game.save(update_fields=['joinable'])
        return player

    def _create_starting_fleets(self, player):
        count = max(0, int(player.starting_fleets or 0))
        if count <= 0:
            return
        tech_effects = get_player_tech_effects(player)
        fleet_start_index = player.fleets.count()
        for i in range(count):
            fleet_number = fleet_start_index + i + 1
            fleet_name = f"{player.name} Fleet {fleet_number}"
            thumbnail_path = choose_fleet_thumbnail(
                f"{self.game.id}:{player.id}:{fleet_name}",
                tech_effects.get('hull_thumbnail_class'),
            )
            Fleet.objects.create(
                game=self.game,
                player=player,
                name=fleet_name,
                x=player.homeworld.x,
                y=player.homeworld.y,
                cargo_capacity=tech_effects.get('max_cargo_capacity', 100),
                fuel=tech_effects.get('max_fuel', 50.0),
                max_fuel=tech_effects.get('max_fuel', 50.0),
                max_safe_warp=tech_effects.get('max_warp_speed', 2),
                fuel_efficiency=tech_effects.get('fuel_efficiency', 1.0),
                overmax_fuel_penalty=tech_effects.get('overmax_fuel_penalty', 1.0),
                warp_advantage=combine_speed_advantages(
                    getattr(player.race_type, 'warp_advantage', 0.0) or 0.0,
                    tech_effects.get('warp_advantage', 0.0) or 0.0,
                ),
                wormhole_fuel_per_ly=tech_effects.get('wormhole_fuel_per_ly', 5.0),
                wormhole_destruction_chance=tech_effects.get('wormhole_destruction_chance', 0.0),
                offense_level=tech_effects.get('offense_level', 0.0),
                defense_level=tech_effects.get('defense_level', 0.0),
                has_bombs=tech_effects.get('has_bombs'),
                has_miners=tech_effects.get('has_miners'),
                has_fuel_factory=bool(tech_effects.get('has_fuel_factory')),
                fuel_factory_mg_per_year=tech_effects.get(
                    'fuel_factory_mg_per_year', 0.0
                ),
                fuel_factory_max_warp=tech_effects.get(
                    'fuel_factory_max_warp', -1
                ),
                has_wormhole_drive=bool(tech_effects.get('has_wormhole_drive')),
                max_cloaked_warp=tech_effects.get('max_cloaked_warp', -1),
                advanced_cloak=bool(tech_effects.get('advanced_cloak')),
                basic_scanner_range=tech_effects.get('basic_scanner_range', 0),
                advanced_scanner_range=tech_effects.get('advanced_scanner_range', 0),
                thumbnail_path=thumbnail_path,
            )
    
    def _create_random_fleets(self, count_per_player):
        """Create fleets for each player. Game must be saved first. For testing."""
        for player in self.game.players.all():
            for _ in range(count_per_player):
                Fleet.objects.create(
                    game=self.game,
                    player=player,
                    name=self.starnamer.get_unique(),
                    x=random.randint(1, self.game.map_size_x),
                    y=random.randint(1, self.game.map_size_y),
                    # Add some random cargo for testing
                    ironium_inventory=random.randint(0, 10000),
                    boranium_inventory=random.randint(0, 10000),
                    germanium_inventory=random.randint(0, 5000),
                    colonists=random.randint(0, 5000)
                )
        return self
