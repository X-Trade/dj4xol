from datetime import timedelta
from math import atan2, ceil, degrees, log2
from numpy import array as nparray, linalg
from django.db import models
from django.utils import timezone

from .messages import (
    EnvironmentalDeathMessageFactory,
    OvercrowdingDeathMessageFactory,
    ColonyAbandonedMessageFactory,
    PlanetoidEventMessageFactory,
    PopulationBoomMessageFactory,
    MiningDiscoveryMessageFactory,
    ColonyVanishedMessageFactory,
    MiningAccidentDeathsMessageFactory,
    MiningAccidentResourcesMessageFactory,
    FleetBuiltMessageFactory,
    FleetLostMessageFactory,
    FleetColonisedMessageFactory,
    ColoniseFailedAlreadyOwnedMessageFactory,
    ColoniseFailedNoStarMessageFactory,
    ColoniseFailedNoColonistsMessageFactory,
    ColonistsLostInSpaceMessageFactory,
    ColonistsFailedToColoniseMessageFactory,
    ColonistsUnexpectedColonyMessageFactory,
    MineralGiftMessageFactory,
    ProductionSummaryMessageFactory,
    ProductionOrdersCompletedMessageFactory,
    FleetWarpDamageMessageFactory,
    FleetBussardRecoveryMessageFactory,
    FleetWarpDestroyedMessageFactory,
    FleetMergedMessageFactory,
    FleetOrdersCompletedMessageFactory,
    FleetBuildBlockedNoShipyardMessageFactory,
    FleetRepairedMessageFactory,
    OrbitalDefenseHitMessageFactory,
    FleetBombardmentReportMessageFactory,
    BombardFailedNoStarMessageFactory,
    StarVanishedOminousMessageFactory,
    ResearchLevelUnlockedMessageFactory,
    ResearchBreakthroughMessageFactory,
)
import random

from .colony_rules import (
    BILLION,
    MILLION,
    DEFAULT_SOFT_CAP,
    YIELD_DEPLETION_RATE,
    HOMEWORLD_MIN_YIELD,
    capacity_modifier,
    effective_capacity,
    habitability_proportion,
    calculate_employment_percent,
    COLONISTS_PER_JOB,
    COLONISTS_PER_SHIPYARD,
    calculate_available_buildpoints,
    calculate_available_researchpoints,
    calculate_staffing_ratio,
    calculate_productivity_multiplier,
    calculate_consumed_buildpoints,
    calculate_productivity_percent,
    calculate_economy_percent,
    calculate_economy_factor,
    calculate_habitability_factor,
    calculate_growth_factor,
    calculate_effective_defenses,
    OVERMINING_DEPLETION_MULTIPLIER,
)
from .research import (
    process_player_research_for_year,
    get_player_tech_effects,
    get_player_colony_defense_level,
    apply_research_bonus_rp,
)
from .fleet_thumbnails import choose_fleet_thumbnail
from .chance_rules import (
    roll_chance as chance_roll,
    scaled_luck_roll,
    luck_ratio_chance,
)
from .bombardment_rules import (
    bombardment_damage_k,
    normalize_bomb_type,
    normalize_miner_type,
    smart_bombs_only_target_defenses_and_population,
)

# Population carrying capacity constants now live in colony_rules.py

TURN_INTERVALS = {
    'HOURLY': timedelta(hours=1),
    'DAILY': timedelta(days=1),
    'WEEKLY': timedelta(weeks=1),
}

# Random event probability per colonized star per turn
RANDOM_EVENT_CHANCE = 0.01  # 1%
RESEARCH_BREAKTHROUGH_CHANCE = 0.08  # 8% per player-year with active labs

# Mining constants
KT_PER_MINE = 10  # kt per mine per turn

# Warp damage constants
WARP_DESTRUCTION_THRESHOLD = 10  # Warp speed at which destruction becomes possible
WARP_DESTRUCTION_CHANCE = 0.30   # 30% chance of instant destruction at warp >= 10
WARP_DAMAGE_CHANCE_PER_EXCESS = 0.15  # 15% damage chance per excess warp factor

# Salvage constants
SALVAGE_CHANCE_WARP = 0.66       # 66% chance of salvage from warp destruction
SALVAGE_CHANCE_SCUTTLE = 0.33   # 33% chance of salvage from scuttling
SALVAGE_DEGRADATION_MIN = 0.30  # Minimum 30% loss when creating salvage
SALVAGE_DEGRADATION_MAX = 0.70  # Maximum 70% loss when creating salvage

# Combat constants (MVP)
COMBAT_COUNT_SOFTENING = 2.0    # Higher values mean stronger diminishing returns
COMBAT_DAMAGE_SCALE = 30        # Integrity damage per point of opponent strength
COMBAT_SALVAGE_DAMAGE_CHANCE = 0.25
COMBAT_SALVAGE_DAMAGE_FACTOR = 0.20
COMBAT_SHIP_LOSS_MAX_CHANCE = 0.50
COMBAT_LUCK_JITTER = 0.12
COMBAT_ATTACK_ROLL_BEND = 1.0
COMBAT_DEFENSE_ROLL_BEND = 1.0
ORBITAL_DEFENSE_HAZARD_BASE_CHANCE = 0.15
ORBITAL_DEFENSE_HAZARD_MIN_CHANCE = 0.10
ORBITAL_DEFENSE_HAZARD_MAX_CHANCE = 0.20
ORBITAL_DEFENSE_HAZARD_DAMAGE_FACTOR = 0.25
MERGE_COMBAT_RETENTION = 0.95
BUSSARD_RECOVERY_CHANCE = 0.5
BUSSARD_RECOVERY_MIN_MG = 1
BUSSARD_RECOVERY_MAX_MG = 5
NOVA_STAR_DESTRUCTION_CHANCE = 0.40
STAR_VANISH_FLEET_MENTION_CHANCE = 0.35
REMOTE_MINER_UNITS_BY_TYPE = {
    'SMALL': 1,
    'MEDIUM': 2,
    'LARGE': 4,
}
REMOTE_MINE_HARASS_CHANCE = 0.35
REMOTE_MINE_HARASS_DAMAGE_FACTOR = 0.25
REMOTE_MINE_DEFENSE_DAMAGE_MULTIPLIER = 1.25


# Chance calculation functions (separated for testability)
def roll_chance(threshold):
    """Return True if random roll is below threshold."""
    return chance_roll(threshold)


def roll_attack_scale(luck_multiplier):
    """Roll a 0..1 attack scale, biased by luck.

    Offense tech/race sets a maximum attack multiplier. Each engagement
    samples a scale beneath that maximum. Luck > 1 biases higher rolls,
    luck < 1 biases lower rolls.
    """
    # Keep offense chance-based without overwhelming deterministic strength deltas.
    # Scale range is 0.5..1.0 where 1.0 is the configured maximum force.
    return scaled_luck_roll(
        luck_multiplier,
        min_scale=0.5,
        max_scale=1.0,
        bend=COMBAT_ATTACK_ROLL_BEND,
    )


def roll_defense_scale(luck_multiplier):
    """Roll defense effectiveness scale for the side taking damage."""
    return scaled_luck_roll(
        luck_multiplier,
        min_scale=0.5,
        max_scale=1.0,
        bend=COMBAT_DEFENSE_ROLL_BEND,
    )


def calculate_integrity_loss(excess_warp):
    """Calculate integrity loss from warp damage (5-15% per excess warp)."""
    return sum(random.randint(5, 15) for _ in range(excess_warp))


def calculate_cargo_loss_percent(excess_warp):
    """Calculate cargo loss percentage from warp damage (2-10% per excess warp)."""
    return sum(random.randint(2, 10) for _ in range(excess_warp)) / 100.0


def calculate_salvage_minerals(dry_mass, cargo_iron, cargo_bor, cargo_germ):
    """Calculate salvage minerals from a destroyed/scuttled fleet.

    Uses the same dry_mass split formula as colonise (random distribution).
    Applies random degradation (30-70% loss) to simulate battle damage.
    Returns (ironium, boranium, germanium) tuple.
    """
    # Split dry_mass into mineral bonuses (same formula as colonise)
    bonus_ironium = random.randint(0, dry_mass)
    remaining = dry_mass - bonus_ironium
    bonus_boranium = random.randint(0, remaining)
    bonus_germanium = remaining - bonus_boranium

    # Total minerals before degradation
    total_iron = cargo_iron + bonus_ironium
    total_bor = cargo_bor + bonus_boranium
    total_germ = cargo_germ + bonus_germanium

    # Apply random degradation (30-70% survives)
    survival_rate = random.uniform(
        1.0 - SALVAGE_DEGRADATION_MAX,
        1.0 - SALVAGE_DEGRADATION_MIN
    )
    return (
        int(total_iron * survival_rate),
        int(total_bor * survival_rate),
        int(total_germ * survival_rate),
    )


def normalize_ship_count(ship_count):
    """Normalize ship count with diminishing returns and no hard cap.

    The curve is scaled so that 2 ships maps to 1.0:
    f(n) = 2n / (n + COMBAT_COUNT_SOFTENING)
    """
    if ship_count <= 0:
        return 0.0
    n = float(ship_count)
    return (2.0 * n) / (n + COMBAT_COUNT_SOFTENING)


def tech_level_to_multiplier(level):
    """Convert log2 tech level to linear multiplier."""
    try:
        value = float(level)
    except (TypeError, ValueError):
        value = 0.0
    return 2.0 ** max(0.0, value)


def multiplier_to_tech_level(multiplier):
    """Convert linear multiplier back to log2 tech level."""
    try:
        value = float(multiplier)
    except (TypeError, ValueError):
        value = 1.0
    # Keep merged values in supported range for combat multipliers.
    return max(0.0, log2(max(1.0, value)))


def calculate_fleet_attack_multiplier(fleet):
    """Return combined attack multiplier from race + fleet tech."""
    race_mult = fleet.player.race_type.combat_multiplier
    return race_mult * tech_level_to_multiplier(fleet.offense_level)


def calculate_fleet_defense_multiplier(fleet):
    """Return combined defense multiplier from race + fleet tech."""
    race_mult = fleet.player.race_type.defence_multiplier
    return race_mult * tech_level_to_multiplier(fleet.defense_level)


def calculate_fleet_strength(fleet, opponent_defence_multiplier, attack_roll_scale=1.0):
    """Calculate fleet combat strength against opponent defenses."""
    count_norm = normalize_ship_count(fleet.ship_count)
    integrity_norm = max(0.0, min(1.0, fleet.integrity / 100.0))
    attack_mult = calculate_fleet_attack_multiplier(fleet)
    try:
        scale = float(attack_roll_scale)
    except (TypeError, ValueError):
        scale = 1.0
    scale = max(0.0, min(1.0, scale))
    attack_mult *= scale
    defence_factor = 1.0 / opponent_defence_multiplier if opponent_defence_multiplier else 1.0
    base = count_norm * attack_mult * defence_factor
    integrity_factor = (2.0 * integrity_norm) - (integrity_norm ** 2)
    strength = base * integrity_factor
    return max(0.0, strength)


class GameTurn():
    """Generate a turn for a game."""
    def __init__(self, game):
        self.game = game

    def generate_turn(self):
        """Generate a turn for the game. Requires at least one player."""
        if self.game.is_generating:
            raise Exception("Turn generation already in progress")
        if not self.game.players.exists():
            raise Exception("cannot generate turn for game with no players")

        self.game.is_generating = True
        self.game.save(update_fields=['is_generating'])

        for _ in range(self.game.years_per_turn):
            self._process_year()
        self.game.last_generated = timezone.now()
        self.game.next_generation = self._calculate_next_generation()
        self._reset_turn_ins()
        self.game.is_generating = False
        self.game.save()

    def _process_year(self):
        """Process a single year of game time."""
        self.fleet_movements()
        self.check_lost_fleets()
        self.check_damaged_fleets()
        self.first_contact_checks()
        self.resolve_combat()
        self.resolve_orbital_defense_hazards()
        self.mining()
        self.production()
        self.research()
        self.population_growth()
        self.random_events()
        self.clear_empty_planets()
        self.check_join_deadline()
        self.generate_reports()
        self.game.year += 1

    def _calculate_next_generation(self):
        """Calculate next generation time based on turn scheme."""
        interval = TURN_INTERVALS.get(self.game.turn_scheme)
        return timezone.now() + interval if interval else None

    def _reset_turn_ins(self):
        """Reset turned_in status and update message visibility for all players."""
        for player in self.game.players.all():
            player.turned_in = False
            player.messages_seen_year = player.last_seen_year
            player.save(update_fields=['turned_in', 'messages_seen_year'])

    def generate_reports(self):
        """Generate exploration reports for all fleets at their current locations."""
        from .models import Fleet
        for fleet in Fleet.objects.filter(game=self.game):
            self._generate_reports_for_fleet(fleet)

    def _generate_reports_for_fleet(self, fleet):
        """Generate reports for all objects at fleet's location."""
        from .models import Star, Salvage, Fleet

        x, y = fleet.x, fleet.y
        player = fleet.player
        year = self.game.year

        # Report on all stars at this location
        for star in Star.objects.filter(game=self.game, x=x, y=y):
            self._create_or_update_report(player, 'star', star, year)

        # Report on other players' fleets at this location
        for other_fleet in Fleet.objects.filter(
            game=self.game, x=x, y=y
        ).exclude(player=player):
            self._create_or_update_report(player, 'fleet', other_fleet, year)

        # Report on all salvage at this location
        for salvage in Salvage.objects.filter(game=self.game, x=x, y=y):
            self._create_or_update_report(player, 'salvage', salvage, year)

    def _create_or_update_report(self, player, target_type, obj, year):
        """Create or update a report for an object."""
        from .models import Report, Fleet
        from .messages import HabitableWorldMessageFactory

        report_data = self._build_report_data(player, obj, target_type)

        report, created = Report.objects.update_or_create(
            player=player,
            target_type=target_type,
            target_id=obj.id,
            defaults={
                'game': self.game,
                'year': year,
            }
        )
        report.set_report_data(report_data)
        report.save()

        if created and target_type == 'star' and calculate_habitability_factor(player, obj) >= 0 and obj.player != player:
            fleet = Fleet.objects.filter(game=self.game, player=player, x=obj.x, y=obj.y).first()
            if fleet:
                factory = HabitableWorldMessageFactory(self.game, player, fleet, obj)
                msg = factory.new_message()
                msg.year = self.game.year
                msg.save()

    def _build_report_data(self, player, obj, target_type):
        """Build the data dict to cache in a report."""
        if target_type == 'star':
            jobs = ((obj.mines + obj.factories + obj.labs + obj.defenses) * COLONISTS_PER_JOB
                    + obj.shipyards * COLONISTS_PER_SHIPYARD)
            employment = calculate_employment_percent(obj)
            return {
                'name': obj.name,
                'x': obj.x,
                'y': obj.y,
                'colonists': obj.colonists,
                'capacity': effective_capacity(player, obj),
                'is_survivable': calculate_habitability_factor(player, obj) >= 0,
                'player_name': obj.player.name if obj.player else None,
                'gravity': obj.gravity,
                'temperature': obj.temperature,
                'radiation': obj.radiation,
                'ironium_yield': obj.ironium_yield,
                'boranium_yield': obj.boranium_yield,
                'germanium_yield': obj.germanium_yield,
                'ironium_inventory': obj.ironium_inventory,
                'boranium_inventory': obj.boranium_inventory,
                'germanium_inventory': obj.germanium_inventory,
                # Infrastructure snapshot (matches visible Detail panel values).
                'mines': obj.mines,
                'factories': obj.factories,
                'factories_bp': calculate_available_buildpoints(obj),
                'labs': obj.labs,
                'labs_rp': calculate_available_researchpoints(obj),
                'defenses': obj.defenses,
                'defenses_tooltip': None,
                'shipyards': obj.shipyards,
                'jobs_count': jobs,
                'jobs_employment': employment,
            }
        elif target_type == 'fleet':
            offense_mod = int(round(float(obj.offense_level) * 10.0))
            defense_mod = int(round(float(obj.defense_level) * 10.0))
            return {
                'name': obj.name,
                'x': obj.x,
                'y': obj.y,
                'player_name': obj.player.name if obj.player else None,
                'ship_count': obj.ship_count,
                'max_safe_warp': obj.max_safe_warp,
                'integrity': obj.integrity,
                'offense_modifier': f'{offense_mod:+d}',
                'defense_modifier': f'{defense_mod:+d}',
                'has_bombs': obj.has_bombs,
                'has_miners': obj.has_miners,
                'has_fuel_factory': bool(obj.has_fuel_factory),
                'has_wormhole_drive': bool(obj.has_wormhole_drive),
            }
        elif target_type == 'salvage':
            return {
                'name': obj.name,
                'x': obj.x,
                'y': obj.y,
                'ironium_inventory': obj.ironium_inventory,
                'boranium_inventory': obj.boranium_inventory,
                'germanium_inventory': obj.germanium_inventory,
                'total_minerals': obj.total_minerals,
            }
        return {}

    def check_quorum(self):
        """Check if all players have turned in. Returns True if quorum met."""
        if self.game.turn_scheme != 'QUORUM':
            return False
        total = self.game.players.count()
        turned_in = self.game.players.filter(turned_in=True).count()
        return total > 0 and turned_in == total

    def generate_turns(self, turns):
        """Generate multiple turns for the game."""
        for _ in range(turns):
            self.generate_turn()

    def fleet_movements(self):
        """Move fleets according to their orders."""
        self._locked_fleet_ids_for_year = set()
        self._fleet_start_positions_for_year = {
            fleet.id: (fleet.x, fleet.y) for fleet in self.game.fleets.all()
        }
        # Get fleet IDs first, then fetch fresh for each processing
        # This ensures we see changes made by other fleet's transfers
        fleet_ids = list(self.game.fleets.values_list('id', flat=True))
        random.shuffle(fleet_ids)
        for fleet_id in fleet_ids:
            try:
                fleet = self.game.fleets.get(id=fleet_id)
            except self.game.fleets.model.DoesNotExist:
                continue  # Fleet was deleted (e.g., by colonise order)
            if fleet.id in self._locked_fleet_ids_for_year:
                self._refuel_fleet_if_in_friendly_shipyard_orbit(fleet)
                fleet.save()
                continue
            result = self.move_fleet(fleet)
            if result is not None:
                self._refuel_fleet_if_in_friendly_shipyard_orbit(result)
                result.save()

    def _refuel_fleet_if_in_friendly_shipyard_orbit(self, fleet):
        """Refuel fleets that end the turn in orbit of a friendly shipyard colony."""
        from .models import Star

        can_refuel = Star.objects.filter(
            game=self.game,
            x=fleet.x,
            y=fleet.y,
            player=fleet.player,
            shipyards__gt=0,
        ).exists()
        if can_refuel:
            fleet.fuel = fleet.max_fuel

    def check_lost_fleets(self):
        """Remove fleets that have moved beyond map boundaries."""
        max_x = self.game.map_size_x
        max_y = self.game.map_size_y
        for fleet in self.game.fleets.all():
            if fleet.x < 0 or fleet.x >= max_x or fleet.y < 0 or fleet.y >= max_y:
                self._create_fleet_lost_message(fleet)
                fleet.delete()

    def _create_fleet_lost_message(self, fleet):
        """Create a message for a fleet lost beyond map boundaries."""
        factory = FleetLostMessageFactory(self.game, fleet.player, fleet.name)
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def check_damaged_fleets(self):
        """Destroy any fleets with zero integrity."""
        for fleet in self.game.fleets.filter(integrity__lte=0):
            self._handle_warp_destruction(fleet, warp_speed=0, from_damage=True)

    def resolve_combat(self):
        """Resolve combat at any location with fleets from 2+ players."""
        from .models import Fleet
        fleets = list(Fleet.objects.filter(game=self.game))
        locations = {}
        for fleet in fleets:
            locations.setdefault((fleet.x, fleet.y), []).append(fleet)

        for (x, y), loc_fleets in locations.items():
            players = {fleet.player_id for fleet in loc_fleets}
            if len(players) < 2:
                continue
            self._resolve_battle_at_location(x, y, loc_fleets)

    def first_contact_checks(self):
        """Send first contact messages before combat resolves."""
        from .models import Fleet, Star, Report
        from .messages import FirstContactFleetMessageFactory, FirstContactStarMessageFactory

        handled = set()
        fleets = list(Fleet.objects.filter(game=self.game))
        first_any_available = {}
        contacted_races_seen = {}

        def has_contact_with_race(player, other_player):
            """Return True if player has previously reported an object owned by other_player."""
            fleet_ids = list(
                Fleet.objects.filter(game=self.game, player=other_player)
                .values_list('id', flat=True)
            )
            star_ids = list(
                Star.objects.filter(game=self.game, player=other_player)
                .values_list('id', flat=True)
            )
            target_ids = fleet_ids + star_ids
            if not target_ids:
                return False
            return Report.objects.filter(
                player=player,
                target_type__in=['fleet', 'star'],
                target_id__in=target_ids
            ).exists()

        for fleet in fleets:
            player = fleet.player
            x, y = fleet.x, fleet.y
            if player.id not in first_any_available:
                first_any_available[player.id] = (not self._player_has_other_contacts(player))
            if player.id not in contacted_races_seen:
                contacted_races_seen[player.id] = set()

            # Star contact
            for star in Star.objects.filter(game=self.game, x=x, y=y).exclude(player=player).exclude(player__isnull=True):
                race_id = star.player_id
                if race_id in contacted_races_seen[player.id]:
                    continue
                if has_contact_with_race(player, star.player):
                    contacted_races_seen[player.id].add(race_id)
                    continue
                key = (player.id, 'star', star.id)
                if key in handled:
                    continue
                if Report.objects.filter(player=player, target_type='star', target_id=star.id).exists():
                    continue
                first_any = first_any_available[player.id]
                factory = FirstContactStarMessageFactory(self.game, player, fleet, star, first_any=first_any)
                msg = factory.new_message()
                msg.year = self.game.year
                msg.save()
                handled.add(key)
                contacted_races_seen[player.id].add(race_id)
                if first_any_available[player.id]:
                    first_any_available[player.id] = False

            # Fleet contact
            for other in Fleet.objects.filter(game=self.game, x=x, y=y).exclude(player=player):
                race_id = other.player_id
                if race_id in contacted_races_seen[player.id]:
                    continue
                if has_contact_with_race(player, other.player):
                    contacted_races_seen[player.id].add(race_id)
                    continue
                key = (player.id, 'fleet', other.id)
                if key in handled:
                    continue
                if Report.objects.filter(player=player, target_type='fleet', target_id=other.id).exists():
                    continue
                first_any = first_any_available[player.id]
                factory = FirstContactFleetMessageFactory(self.game, player, fleet, other, first_any=first_any)
                msg = factory.new_message()
                msg.year = self.game.year
                msg.save()
                handled.add(key)
                contacted_races_seen[player.id].add(race_id)
                if first_any_available[player.id]:
                    first_any_available[player.id] = False

    def _player_has_other_contacts(self, player):
        """Return True if player has seen any other player's star/fleet before."""
        from .models import Report, Fleet, Star
        other_fleet_ids = list(
            Fleet.objects.filter(game=self.game)
            .exclude(player=player)
            .values_list('id', flat=True)
        )
        other_star_ids = list(
            Star.objects.filter(game=self.game)
            .exclude(player=player)
            .exclude(player__isnull=True)
            .values_list('id', flat=True)
        )
        return Report.objects.filter(
            player=player,
            target_type__in=['fleet', 'star'],
            target_id__in=(other_fleet_ids + other_star_ids)
        ).exists()

    def _resolve_battle_at_location(self, x, y, fleets):
        """Resolve a single battle at a location."""
        from .messages import CombatMessageFactory
        from .models import Star

        fleets_by_player = {}
        for fleet in fleets:
            fleets_by_player.setdefault(fleet.player, []).append(fleet)

        players = sorted(fleets_by_player.keys(), key=lambda p: p.id)
        if len(players) < 2:
            return

        strength_by_player = {}
        for player in players:
            opponent_fleets = []
            for opponent in players:
                if opponent == player:
                    continue
                opponent_fleets.extend(fleets_by_player[opponent])
            if opponent_fleets:
                total_enemy_ships = sum(max(1, f.ship_count) for f in opponent_fleets)
                weighted_enemy_def = sum(
                    calculate_fleet_defense_multiplier(f) *
                    roll_defense_scale(
                        getattr(f.player.race_type, 'luck_multiplier', 1.0)
                    ) *
                    max(1, f.ship_count)
                    for f in opponent_fleets
                ) / float(total_enemy_ships)
                opponent_defence = weighted_enemy_def
            else:
                opponent_defence = 1.0
            strength_by_player[player] = sum(
                calculate_fleet_strength(
                    fleet,
                    opponent_defence,
                    attack_roll_scale=roll_attack_scale(
                        getattr(fleet.player.race_type, 'luck_multiplier', 1.0)
                    ),
                )
                for fleet in fleets_by_player[player]
            )

        winner = self._choose_combat_winner(players, strength_by_player)
        damage_taken = self._calculate_combat_damage(strength_by_player)
        results = self._apply_combat_damage(fleets_by_player, damage_taken)

        star = Star.objects.filter(game=self.game, x=x, y=y).first()
        location = star if star else (x, y)

        for player in players:
            result = results[player]
            opponent_names = sorted({opponent.name for opponent in players if opponent != player})
            enemy_integrity_lost = 0
            enemy_ships_lost = 0
            enemy_fleets_destroyed = 0
            for opponent in players:
                if opponent == player:
                    continue
                enemy_result = results[opponent]
                enemy_integrity_lost += enemy_result['integrity_lost']
                enemy_ships_lost += enemy_result['ships_lost']
                enemy_fleets_destroyed += enemy_result['fleets_destroyed']
            factory = CombatMessageFactory(
                self.game,
                player,
                winner=winner,
                location=location,
                opponents=opponent_names,
                fleets_destroyed=result['fleets_destroyed'],
                ships_lost=result['ships_lost'],
                integrity_lost=result['integrity_lost'],
                enemy_fleets_destroyed=enemy_fleets_destroyed,
                enemy_ships_lost=enemy_ships_lost,
                enemy_integrity_lost=enemy_integrity_lost,
                salvage_created=result['salvage_created'],
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()

    def _choose_combat_winner(self, players, strength_by_player):
        """Choose a winner weighted by strength."""
        weighted_strengths = {}
        for player in players:
            base_strength = strength_by_player[player]
            luck = player.race_type.luck_multiplier
            jitter = random.uniform(-COMBAT_LUCK_JITTER, COMBAT_LUCK_JITTER) * luck
            weighted_strengths[player] = max(0.0, base_strength * (1.0 + jitter))

        total_strength = sum(weighted_strengths.values())
        if total_strength <= 0:
            return random.choice(players)

        roll = random.uniform(0, total_strength)
        cumulative = 0.0
        for player in players:
            cumulative += weighted_strengths[player]
            if roll <= cumulative:
                return player
        return players[-1]

    def _calculate_combat_damage(self, strength_by_player):
        """Calculate damage each player takes based on absolute opponents' strength.

        This intentionally avoids a fixed shared damage pool, so overwhelming
        strength can decisively destroy weaker fleets in a single engagement.
        """
        total_strength = sum(strength_by_player.values())
        if total_strength <= 0:
            per_player = COMBAT_DAMAGE_SCALE / max(1, len(strength_by_player))
            return {player: per_player for player in strength_by_player}

        damage_taken = {}
        for player, strength in strength_by_player.items():
            opponent_strength = total_strength - strength
            relative_share = max(0.0, opponent_strength / total_strength)
            intensity = 1.0 + max(0.0, opponent_strength)
            damage_taken[player] = COMBAT_DAMAGE_SCALE * relative_share * intensity
        return damage_taken

    def _apply_combat_damage(self, fleets_by_player, damage_taken):
        """Apply combat damage to fleets and return summary results."""
        results = {}
        for player, fleets in fleets_by_player.items():
            total_ships = sum(fleet.ship_count for fleet in fleets) or 1
            total_integrity_loss = 0
            ships_lost = 0
            fleets_destroyed = 0
            salvage_created = False

            for fleet in fleets:
                share = fleet.ship_count / total_ships
                integrity_loss = int(round(damage_taken[player] * share))
                if damage_taken[player] > 0 and integrity_loss == 0:
                    integrity_loss = 1

                total_integrity_loss += integrity_loss
                old_integrity = fleet.integrity
                fleet.integrity = max(0, fleet.integrity - integrity_loss)

                if fleet.integrity <= 0:
                    if self._handle_combat_destruction(fleet):
                        salvage_created = True
                    fleets_destroyed += 1
                    continue

                ship_loss = self._maybe_reduce_ship_count(fleet)
                if ship_loss:
                    ships_lost += ship_loss

                if integrity_loss > 0 and self._maybe_create_combat_salvage(fleet, integrity_loss):
                    salvage_created = True

                fleet.save(update_fields=['integrity', 'ship_count'])

            results[player] = {
                'integrity_lost': total_integrity_loss,
                'ships_lost': ships_lost,
                'fleets_destroyed': fleets_destroyed,
                'salvage_created': salvage_created,
            }
        return results

    def _handle_combat_destruction(self, fleet):
        """Destroy fleet from combat and create salvage (always)."""
        salvage_result = self._create_salvage_from_fleet(fleet)
        fleet.delete()
        return bool(salvage_result)

    def _maybe_reduce_ship_count(self, fleet):
        """If integrity is low, there is a chance of losing a ship."""
        if fleet.integrity >= 50 or fleet.ship_count <= 1:
            return 0
        chance = min(COMBAT_SHIP_LOSS_MAX_CHANCE, (50 - fleet.integrity) / 100.0)
        if roll_chance(chance):
            fleet.ship_count -= 1
            return 1
        return 0

    def _maybe_create_combat_salvage(self, fleet, integrity_loss):
        """Chance to create a small amount of salvage based on damage dealt."""
        if not roll_chance(COMBAT_SALVAGE_DAMAGE_CHANCE):
            return False

        damage_fraction = max(0.0, min(1.0, integrity_loss / 100.0))
        if damage_fraction == 0:
            return False

        salvage_dry_mass = int(fleet.dry_mass * damage_fraction * COMBAT_SALVAGE_DAMAGE_FACTOR)
        salvage_iron = int(fleet.ironium_inventory * damage_fraction * COMBAT_SALVAGE_DAMAGE_FACTOR)
        salvage_bor = int(fleet.boranium_inventory * damage_fraction * COMBAT_SALVAGE_DAMAGE_FACTOR)
        salvage_germ = int(fleet.germanium_inventory * damage_fraction * COMBAT_SALVAGE_DAMAGE_FACTOR)

        if salvage_dry_mass == 0 and salvage_iron == 0 and salvage_bor == 0 and salvage_germ == 0:
            return False

        iron, bor, germ = calculate_salvage_minerals(
            salvage_dry_mass, salvage_iron, salvage_bor, salvage_germ
        )
        if iron == 0 and bor == 0 and germ == 0:
            return False

        self._create_salvage_at_location(fleet.x, fleet.y, iron, bor, germ)
        return True

    def _create_salvage_at_location(self, x, y, iron, bor, germ):
        """Create salvage at location, or deposit on star if present."""
        from .models import Star, Salvage
        if iron == 0 and bor == 0 and germ == 0:
            return None

        star = Star.objects.filter(game=self.game, x=x, y=y).first()
        if star:
            star.ironium_inventory += iron
            star.boranium_inventory += bor
            star.germanium_inventory += germ
            star.save()
            return star

        salvage, created = Salvage.objects.get_or_create(
            game=self.game, x=x, y=y,
            defaults={
                'ironium_inventory': iron,
                'boranium_inventory': bor,
                'germanium_inventory': germ,
            }
        )
        if not created:
            salvage.ironium_inventory += iron
            salvage.boranium_inventory += bor
            salvage.germanium_inventory += germ
            salvage.save()
        return salvage

    def move_fleet(self, fleet):
        """Process fleet orders.

        Allows passthrough of non-move orders in a single turn, but only one
        move-type order (MOVE/INTERCEPT/PATROL) may execute per turn.
        """
        had_orders = fleet.orders.exists()
        result = self._move_fleet_single_order(fleet)

        if result is not None and had_orders and not result.orders.exists():
            self._create_fleet_orders_completed_message(result)

        return result

    def _create_fleet_orders_completed_message(self, fleet):
        """Create a message when a fleet's order queue is exhausted."""
        factory = FleetOrdersCompletedMessageFactory(self.game, fleet.player, fleet)
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def _move_fleet_single_order(self, fleet):
        """Process fleet orders with one move-like order per turn.

        Non-movement orders can pass through in one turn. Once a MOVE/INTERCEPT/
        PATROL order has executed, subsequent non-movement orders may execute
        immediately, but the next movement order waits for next turn.
        """
        # Snapshot orders at start of turn to avoid processing newly created repeat orders
        # Transfer orders: execute once and continue to next order (passthrough)
        # Move orders: execute once and stop processing (blocking)

        # Snapshot all current orders to prevent processing repeat orders created this turn
        orders_to_process = list(fleet.orders.order_by('position', 'id'))

        movement_executed = False

        for order in orders_to_process:
            # Check if order still exists (might have been deleted by previous processing)
            if not fleet.orders.filter(id=order.id).exists():
                continue

            if order.order_type in ['MOVE', 'INTERCEPT', 'PATROL'] and movement_executed:
                # Exactly one move-like order can execute per turn.
                break

            if order.order_type == 'TRANSFER':
                # Try to execute transfer immediately
                transfer_result = self._try_execute_transfer(fleet, order)
                if transfer_result == 'executed':
                    # Transfer completed - handle repeat and continue to next order
                    self._handle_repeating_order(order)
                    order.delete()
                    continue  # PASSTHROUGH: Continue to next order
                elif transfer_result == 'waiting':
                    # Transfer blocked - stop processing
                    break

            elif order.order_type in ['MOVE', 'INTERCEPT']:
                # Try to execute move order
                move_result = self._move_toward_destination(fleet, order)
                if move_result == 'destroyed':
                    # Fleet destroyed by warp damage
                    return None
                if move_result is True:
                    if order.order_type == 'INTERCEPT':
                        self._lock_successful_enemy_intercept(fleet, order)
                    # Reached destination - handle repeat and passthrough
                    self._handle_repeating_order(order)
                    order.delete()
                    movement_executed = True
                    continue
                # Still moving: block until next turn
                break

            elif order.order_type == 'COLONISE':
                colonise_result = self._try_execute_colonise(fleet, order)
                if colonise_result == 'executed':
                    # Fleet is deleted, return None so caller doesn't try to save it
                    return None
                elif colonise_result == 'waiting':
                    break  # Wait for fleet to reach destination

            elif order.order_type == 'BOMB':
                bomb_result = self._try_execute_bomb(fleet, order)
                if bomb_result == 'executed':
                    # Bombardment completed, removed, and may pass through.
                    continue
                elif bomb_result == 'blocked':
                    # Bombardment remains active and blocks subsequent orders.
                    break
                elif bomb_result == 'fleet_destroyed':
                    return None
                elif bomb_result == 'waiting':
                    break
            elif order.order_type == 'REMOTEMINE':
                mining_result = self._try_execute_remote_mine(fleet, order)
                if mining_result == 'executed':
                    # Mining complete (single-cycle or inventory/full completion): passthrough.
                    continue
                elif mining_result == 'blocked':
                    # Mining queue lock while completion criteria are unmet.
                    break
                elif mining_result == 'fleet_destroyed':
                    return None
                elif mining_result == 'waiting':
                    break

            elif order.order_type == 'MERGE':
                merge_result = self._execute_merge_order(fleet, order)
                if merge_result == 'executed':
                    # Source fleet deleted, return None so caller doesn't save
                    return None
                elif merge_result == 'waiting':
                    break  # Wait for fleets to be at same location
                # 'invalid' falls through to continue to next order

            elif order.order_type == 'SCUTTLE':
                scuttle_result = self._execute_scuttle_order(fleet, order)
                if scuttle_result == 'executed':
                    # Fleet deleted, return None so caller doesn't save
                    return None

            elif order.order_type == 'PATROL':
                patrol_result = self._execute_patrol_order(fleet, order)
                if patrol_result == 'executed':
                    return None
                elif patrol_result == 'moved':
                    movement_executed = True
                    continue
                elif patrol_result == 'blocked':
                    break

            else:
                # Unknown order type, just remove it
                order.delete()
                continue

        return fleet

    def _try_execute_transfer(self, fleet, order):
        """Try to execute a transfer order.

        Transfer orders never move fleets - they only execute when both
        source and target are already at the same location.

        Returns:
        - 'executed': Transfer completed successfully
        - 'waiting': Transfer blocked waiting for target or location
        """
        _, dest_x, dest_y, kind = order.get_actual_target()
        if kind == 'none':
            return 'executed'  # Invalid order, treat as executed to remove it

        # Check if fleet is at the transfer destination
        if fleet.x != dest_x or fleet.y != dest_y:
            # Transfer orders don't move fleets - they wait for manual movement
            return 'waiting'

        # Fleet is at destination, try to execute transfer
        return self._execute_transfer_order(fleet, order)

    def _move_toward_destination(self, fleet, order):
        """Move fleet toward order destination.

        Returns:
            True if destination reached
            False if still moving
            'destroyed' if fleet was destroyed by warp damage
        """
        is_intercept = order.order_type == 'INTERCEPT' and order.target_fleet
        try:
            if is_intercept:
                x, y = self._get_intercept_destination(order)
            else:
                _, x, y, kind = order.get_actual_target()
                if kind == 'none':
                    return True
        except ValueError:
            return True  # Invalid order, treat as reached to remove it

        target = nparray([x, y])
        position = nparray([fleet.x, fleet.y])
        vector = target - position
        distance = linalg.norm(vector)

        # Calculate heading from movement direction (where it's going)
        # 0 = north, 90 = east, 180 = south, 270 = west
        dx, dy = vector[0], vector[1]
        # atan2(dx, -dy) gives angle from north toward target
        fleet.heading = degrees(atan2(dx, -dy)) % 360

        # Check if fleet can reach destination this turn
        warp_speed = order.warpfactor if order.order_type in ['MOVE', 'INTERCEPT'] else 5
        if distance > 0:
            warp_speed = self._resolve_movement_warp_with_fuel(fleet, order, warp_speed)
            if warp_speed <= 0:
                return False

        # If target fleet is already within intercept range, snap directly to it.
        # This avoids "parking ahead" when predictive lead is unnecessary.
        if is_intercept and order.target_fleet:
            target_fleet = order.target_fleet
            live_distance = linalg.norm(
                nparray([target_fleet.x, target_fleet.y]) - position
            )
            if self._is_within_intercept_snap_range(live_distance, warp_speed):
                live_vector = nparray([target_fleet.x, target_fleet.y]) - position
                if linalg.norm(live_vector) > 0:
                    dx, dy = live_vector[0], live_vector[1]
                    fleet.heading = degrees(atan2(dx, -dy)) % 360
                fleet.x = target_fleet.x
                fleet.y = target_fleet.y
                return True

        # Check for warp damage before moving
        damage_result = self._check_warp_damage(fleet, warp_speed, order)
        if damage_result == 'destroyed':
            return 'destroyed'

        if int(distance) <= warp_speed:
            # Fleet reaches destination
            fleet.x = x
            fleet.y = y
            if is_intercept:
                target = order.target_fleet
                if target and (fleet.x, fleet.y) == (target.x, target.y):
                    return True
                return False
            return True
        else:
            # Fleet moves toward destination but doesn't reach it
            normalised_vector = vector / distance
            new_position = position + (normalised_vector * warp_speed)
            new_x = int(new_position[0])
            new_y = int(new_position[1])
            # Ensure progress even with low warp + diagonal movement
            if new_x == fleet.x and new_y == fleet.y:
                step_x = 0 if vector[0] == 0 else (1 if vector[0] > 0 else -1)
                step_y = 0 if vector[1] == 0 else (1 if vector[1] > 0 else -1)
                new_x = fleet.x + step_x
                new_y = fleet.y + step_y
            fleet.x = new_x
            fleet.y = new_y
            if (fleet.x, fleet.y) == (x, y):
                if is_intercept:
                    target = order.target_fleet
                    if target and (fleet.x, fleet.y) == (target.x, target.y):
                        return True
                    return False
                return True
            if is_intercept:
                target = order.target_fleet
                if target and (fleet.x, fleet.y) == (target.x, target.y):
                    return True
            return False

    def _movement_fuel_cost(self, fleet, warp_speed):
        """Fuel used for one year of movement at the specified warp speed."""
        ship_count = max(1, int(fleet.ship_count or 1))
        max_warp = max(1.0, float(fleet.max_safe_warp or 1))
        speed = max(0.0, float(warp_speed or 0.0))

        fuel_efficiency = max(0.05, float(getattr(fleet, 'fuel_efficiency', 1.0) or 1.0))
        overmax_penalty = max(
            0.1, float(getattr(fleet, 'overmax_fuel_penalty', 1.0) or 1.0)
        )

        normalised = speed / max_warp
        cruise_normalised = min(normalised, 1.0)
        # Baseline curve: low warp is cheap, safe warp is around 1.5mg per ship-year.
        cruise_cost = 0.15 + 1.35 * (cruise_normalised ** 1.4)

        overmax_cost = 0.0
        if normalised > 1.0:
            over = normalised - 1.0
            # Exponential overmax burn; propulsion tech can worsen/improve this.
            overmax_cost = overmax_penalty * 0.6 * ((2.0 ** (over * 1.6)) - 1.0)

        per_ship_cost = max(0.05, (cruise_cost + overmax_cost) / fuel_efficiency)
        return per_ship_cost * ship_count

    def _resolve_movement_warp_with_fuel(self, fleet, order, requested_warp):
        """Resolve usable warp for this movement turn based on available fuel."""
        if self._consume_movement_fuel(fleet, requested_warp):
            return requested_warp

        if not roll_chance(BUSSARD_RECOVERY_CHANCE):
            return 0

        fuel_gain = random.randint(BUSSARD_RECOVERY_MIN_MG, BUSSARD_RECOVERY_MAX_MG)
        fleet.fuel = min(float(fleet.max_fuel), float(fleet.fuel) + float(fuel_gain))
        warp = self._max_affordable_warp_speed(fleet, requested_warp)
        if warp <= 0 or not self._consume_movement_fuel(fleet, warp):
            return 0
        self._create_bussard_recovery_message(fleet, fuel_gain, warp, requested_warp)
        return warp

    def _max_affordable_warp_speed(self, fleet, requested_warp):
        """Highest warp (<= requested) this fleet can currently fuel for one turn."""
        fuel = float(fleet.fuel)
        if fuel <= 0.0:
            return 0

        candidate = max(1, int(requested_warp))
        while candidate > 0 and self._movement_fuel_cost(fleet, candidate) > fuel:
            candidate -= 1
        return candidate

    def _consume_movement_fuel(self, fleet, warp_speed):
        """Consume movement fuel; return False when insufficient fuel is available."""
        cost = self._movement_fuel_cost(fleet, warp_speed)
        if float(fleet.fuel) < cost:
            return False
        fleet.fuel = max(0.0, float(fleet.fuel) - cost)
        return True

    def _create_bussard_recovery_message(self, fleet, fuel_gain, warp, requested_warp):
        factory = FleetBussardRecoveryMessageFactory(
            self.game, fleet.player, fleet, fuel_gain, warp, requested_warp
        )
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def _lock_successful_enemy_intercept(self, interceptor, order):
        """Lock both fleets in place after a successful enemy intercept."""
        target = order.target_fleet
        if not target:
            return
        if interceptor.player_id == target.player_id:
            return
        if (interceptor.x, interceptor.y) != (target.x, target.y):
            return
        interceptor_start = self._fleet_start_positions_for_year.get(interceptor.id)
        target_start = self._fleet_start_positions_for_year.get(target.id)
        if interceptor_start is not None and interceptor_start == target_start:
            # If both started stacked this year, don't immobilize the target.
            return

        self._locked_fleet_ids_for_year.add(interceptor.id)
        self._locked_fleet_ids_for_year.add(target.id)

    def _get_intercept_destination(self, order):
        """Calculate intercept destination based on target fleet movement."""
        from math import radians, sin, cos

        if not order.target_fleet:
            _, x, y, kind = order.get_actual_target()
            if kind in ['invalid', 'none']:
                return order.fleet.x, order.fleet.y
            return x, y

        target_fleet = order.target_fleet
        target_speed = self._get_fleet_current_speed(target_fleet)
        if target_speed <= 0:
            return target_fleet.x, target_fleet.y

        if self._is_interceptor_ahead_of_target(order.fleet, target_fleet):
            # Don't keep leading further ahead; turn directly toward target.
            return target_fleet.x, target_fleet.y

        try:
            target_order = target_fleet.orders.order_by('position', 'id').first()
            if target_order:
                _, dest_x, dest_y, kind = target_order.get_actual_target()
                if kind in ['invalid', 'none']:
                    return target_fleet.x, target_fleet.y
                if (target_fleet.x, target_fleet.y) == (dest_x, dest_y):
                    return target_fleet.x, target_fleet.y
        except Exception:
            pass

        theta = radians(target_fleet.heading)
        dx = sin(theta)
        dy = -cos(theta)
        intercept_x = int(target_fleet.x + dx * target_speed)
        intercept_y = int(target_fleet.y + dy * target_speed)
        return intercept_x, intercept_y

    def _is_interceptor_ahead_of_target(self, interceptor, target_fleet):
        """Return True when interceptor is ahead along target's movement vector."""
        from math import radians, sin, cos

        target_speed = self._get_fleet_current_speed(target_fleet)
        if target_speed <= 0:
            return False

        theta = radians(target_fleet.heading)
        movement_vector = nparray([sin(theta), -cos(theta)])
        relative_vector = nparray([
            interceptor.x - target_fleet.x,
            interceptor.y - target_fleet.y,
        ])
        return float(relative_vector.dot(movement_vector)) > 0.0

    def _is_within_intercept_snap_range(self, distance, warp_speed):
        """Return True if intercept can snap to the target this turn.

        Uses a small tolerance before ceil-rounding to avoid near-miss jitter.
        """
        if warp_speed <= 0:
            return False
        rounded_distance = ceil(max(0.0, float(distance) - 0.35))
        return rounded_distance <= int(warp_speed)

    def _get_fleet_current_speed(self, fleet):
        """Return fleet's current movement speed based on its orders."""
        order = fleet.orders.order_by('position', 'id').first()
        if not order:
            return 0
        if order.order_type in ['MOVE', 'INTERCEPT']:
            try:
                _, dest_x, dest_y, kind = order.get_actual_target()
                if kind in ['invalid', 'none']:
                    return 0
                if (fleet.x, fleet.y) == (dest_x, dest_y):
                    return 0
            except Exception:
                return 0
            return order.warpfactor
        return 0

    def _check_warp_damage(self, fleet, warp_speed, order):
        """Check if fleet takes damage from exceeding safe warp speed.

        Returns: 'destroyed', 'damaged', or 'safe'
        """
        if warp_speed <= fleet.max_safe_warp:
            return 'safe'

        excess_warp = warp_speed - fleet.max_safe_warp

        # At warp >= 10 and above safe speed: 30% instant destruction chance
        if warp_speed >= WARP_DESTRUCTION_THRESHOLD:
            if roll_chance(WARP_DESTRUCTION_CHANCE):
                self._handle_warp_destruction(fleet, warp_speed, from_damage=False)
                return 'destroyed'

        # Damage chance: 15% per excess warp factor
        damage_chance = excess_warp * WARP_DAMAGE_CHANCE_PER_EXCESS
        if roll_chance(damage_chance):
            return self._apply_warp_damage(fleet, warp_speed, excess_warp, order)

        return 'safe'

    def _apply_warp_damage(self, fleet, warp_speed, excess_warp, order):
        """Apply damage effects from exceeding safe warp speed.

        Returns: 'destroyed' if integrity drops to 0, 'damaged' otherwise
        """
        integrity_loss = calculate_integrity_loss(excess_warp)
        integrity_loss = min(integrity_loss, fleet.integrity)

        cargo_loss_percent = calculate_cargo_loss_percent(excess_warp)

        cargo_losses = {}
        colonist_deaths = 0

        # Apply cargo losses
        if fleet.ironium_inventory > 0:
            loss = int(fleet.ironium_inventory * cargo_loss_percent)
            if loss > 0:
                cargo_losses['ironium'] = loss
                fleet.ironium_inventory -= loss

        if fleet.boranium_inventory > 0:
            loss = int(fleet.boranium_inventory * cargo_loss_percent)
            if loss > 0:
                cargo_losses['boranium'] = loss
                fleet.boranium_inventory -= loss

        if fleet.germanium_inventory > 0:
            loss = int(fleet.germanium_inventory * cargo_loss_percent)
            if loss > 0:
                cargo_losses['germanium'] = loss
                fleet.germanium_inventory -= loss

        if fleet.colonists > 0:
            colonist_deaths = int(fleet.colonists * cargo_loss_percent)
            if colonist_deaths > 0:
                fleet.colonists -= colonist_deaths

        # Apply integrity damage
        fleet.integrity -= integrity_loss

        # Check if fleet is destroyed
        if fleet.integrity <= 0:
            self._handle_warp_destruction(fleet, warp_speed, from_damage=True)
            return 'destroyed'

        # Reduce warp speed after damage: at least 2, at most max_safe_warp
        reduced_warp = min(max(2, fleet.max_safe_warp // 2), fleet.max_safe_warp)
        if order.warpfactor > reduced_warp:
            order.warpfactor = reduced_warp
            order.save()

        # Create damage message
        self._create_warp_damage_message(
            fleet, warp_speed, integrity_loss, cargo_losses, colonist_deaths
        )
        return 'damaged'

    def _handle_warp_destruction(self, fleet, warp_speed, from_damage=False):
        """Destroy fleet, possibly create salvage, and send destruction message."""
        salvage_created = False
        salvage_location = None

        # 66% chance of salvage from warp destruction
        if roll_chance(SALVAGE_CHANCE_WARP):
            salvage_result = self._create_salvage_from_fleet(fleet)
            if salvage_result:
                salvage_created = True
                salvage_location = salvage_result

        factory = FleetWarpDestroyedMessageFactory(
            self.game, fleet.player, fleet.name, warp_speed,
            fleet.x, fleet.y, from_damage, salvage_created, salvage_location
        )
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()
        fleet.delete()

    def _create_salvage_from_fleet(self, fleet):
        """Create salvage from fleet destruction or scuttling.

        If at a star location, deposits minerals on star surface instead.
        Returns the salvage/star object created/updated, or None if no minerals.
        """
        from .models import Star, Salvage

        iron, bor, germ = calculate_salvage_minerals(
            fleet.dry_mass,
            fleet.ironium_inventory,
            fleet.boranium_inventory,
            fleet.germanium_inventory
        )

        # If no minerals, no salvage created
        if iron == 0 and bor == 0 and germ == 0:
            return None

        # Check for star at location - deposit on surface instead
        star = Star.objects.filter(
            game=self.game, x=fleet.x, y=fleet.y
        ).first()

        if star:
            star.ironium_inventory += iron
            star.boranium_inventory += bor
            star.germanium_inventory += germ
            star.save()
            return star

        # No star - create or add to existing salvage pile
        salvage, created = Salvage.objects.get_or_create(
            game=self.game, x=fleet.x, y=fleet.y,
            defaults={
                'ironium_inventory': iron,
                'boranium_inventory': bor,
                'germanium_inventory': germ,
            }
        )
        if not created:
            # Stack onto existing salvage
            salvage.ironium_inventory += iron
            salvage.boranium_inventory += bor
            salvage.germanium_inventory += germ
            salvage.save()

        return salvage

    def _create_warp_damage_message(self, fleet, warp_speed, integrity_loss,
                                     cargo_losses, colonist_deaths):
        """Create a message for warp damage."""
        factory = FleetWarpDamageMessageFactory(
            self.game, fleet.player, fleet, warp_speed, integrity_loss,
            cargo_losses, colonist_deaths
        )
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def _handle_repeating_order(self, order):
        """Create a repeat copy of the order if needed."""
        if order.repeat:
            from .models import FleetOrders
            # Discard repeat if target no longer exists
            _, _, _, kind = order.get_actual_target()
            if kind in ['invalid', 'none']:
                return
            FleetOrders.objects.create(
                game=self.game,
                fleet=order.fleet,
                order_type=order.order_type,
                repeat=True,
                warpfactor=order.warpfactor,
                x=order.x,
                y=order.y,
                target_star_id=order.target_star_id,
                target_fleet_id=order.target_fleet_id,
                target_salvage_id=order.target_salvage_id,
                transfer_type=order.transfer_type,
                transfer_ironium=order.transfer_ironium,
                transfer_boranium=order.transfer_boranium,
                transfer_germanium=order.transfer_germanium,
                transfer_colonists=order.transfer_colonists,
                patrol_radius=order.patrol_radius,
                intercept_speed=order.intercept_speed,
                bomb_until=order.bomb_until,
                mine_until_full=order.mine_until_full,
            )

    def _execute_transfer_order(self, fleet, order):
        """Execute a transfer order when fleet reaches destination.

        Returns:
        - 'executed': Transfer completed successfully
        - 'waiting': Transfer blocked waiting for target
        """
        from .models import Star, Fleet, Salvage

        # Get the target object based on order parameters
        target_obj, target_x, target_y, target_kind = order.get_actual_target()
        if target_kind == 'none':
            return 'waiting'

        if target_kind == 'space':
            self._transfer_with_space(fleet, order, target_x, target_y)
            return 'executed'

        if order.target_star:
            target_obj = order.target_star
            # Stars don't move, so always available
            if target_obj.x != target_x or target_obj.y != target_y:
                print(f"Warning: Star {target_obj.name} coordinates mismatch")

        elif order.target_fleet:
            target_obj = order.target_fleet
            # Check if target fleet is at expected location
            if target_obj.x != target_x or target_obj.y != target_y:
                print(f"Transfer waiting: Fleet {target_obj.name} not at expected location ({target_x}, {target_y})")
                return 'waiting'  # Block and wait for target fleet to arrive

        elif order.target_salvage:
            target_obj = order.target_salvage
            # Check if salvage still exists at expected location
            if target_obj.x != target_x or target_obj.y != target_y:
                print(f"Warning: Salvage coordinates mismatch")

        else:
            return 'waiting'

        # Verify fleet is actually at the transfer location
        if fleet.x != target_x or fleet.y != target_y:
            print(f"Transfer error: Fleet {fleet.name} not at transfer location")
            return 'executed'  # Remove invalid order

        # Execute transfer based on target type
        if isinstance(target_obj, Star):
            self._transfer_with_star(fleet, order, target_obj)
            return 'executed'
        elif isinstance(target_obj, Fleet):
            self._transfer_with_fleet(fleet, order, target_obj)
            return 'executed'
        elif isinstance(target_obj, Salvage):
            self._transfer_with_salvage(fleet, order, target_obj)
            return 'executed'
        else:
            print(f"Transfer to {type(target_obj)} not yet implemented")
            return 'executed'  # Remove unsupported order

    def _transfer_with_space(self, fleet, order, target_x, target_y):
        """Execute transfer to empty space (creates/updates salvage)."""
        if order.transfer_type not in ('UNLOAD', 'UNLOAD_ALL'):
            return

        if order.transfer_type == 'UNLOAD_ALL':
            ironium_transfer = fleet.ironium_inventory
            boranium_transfer = fleet.boranium_inventory
            germanium_transfer = fleet.germanium_inventory
            colonists_transfer = fleet.colonists
        else:
            ironium_transfer = min(order.transfer_ironium, fleet.ironium_inventory)
            boranium_transfer = min(order.transfer_boranium, fleet.boranium_inventory)
            germanium_transfer = min(order.transfer_germanium, fleet.germanium_inventory)
            colonists_transfer = min(order.transfer_colonists, fleet.colonists)

        if ironium_transfer == 0 and boranium_transfer == 0 and germanium_transfer == 0 and colonists_transfer == 0:
            return

        fleet.ironium_inventory -= ironium_transfer
        fleet.boranium_inventory -= boranium_transfer
        fleet.germanium_inventory -= germanium_transfer
        fleet.colonists -= colonists_transfer
        fleet.save()

        if colonists_transfer > 0:
            factory = ColonistsLostInSpaceMessageFactory(
                self.game, fleet.player, fleet, colonists_transfer, target_x, target_y
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()

        if ironium_transfer or boranium_transfer or germanium_transfer:
            self._create_salvage_at_location(target_x, target_y,
                                             ironium_transfer, boranium_transfer, germanium_transfer)

    def _handle_invasion(self, fleet, star, invader_colonists_kt):
        """Resolve invasion when colonists are transferred to an enemy colony."""
        from .messages import InvasionReportMessageFactory

        if invader_colonists_kt <= 0:
            return

        attacker = fleet.player
        defender = star.player
        defender_race = defender.race_type if defender else None
        attacker_race = attacker.race_type

        fleet_losses_desc = "no fleet losses"
        effective_defenses = calculate_effective_defenses(star)
        if effective_defenses > 0:
            defender_defence_mult = 1.0
            if defender_race:
                defender_defence_mult = defender_race.defence_multiplier
            if defender:
                colony_defense_level = get_player_colony_defense_level(defender)
                defender_defence_mult *= tech_level_to_multiplier(
                    colony_defense_level
                )
            attacker_strength = calculate_fleet_strength(
                fleet,
                defender_defence_mult
            )
            defender_strength = normalize_ship_count(effective_defenses)
            strength_by_player = {
                attacker: attacker_strength,
                defender: defender_strength,
            }
            damage_taken = self._calculate_combat_damage(strength_by_player)
            results = self._apply_combat_damage(
                {attacker: [fleet], defender: []},
                damage_taken
            )
            res = results.get(attacker, {})
            integrity_lost = res.get('integrity_lost', 0)
            ships_lost = res.get('ships_lost', 0)
            fleets_destroyed = res.get('fleets_destroyed', 0)
            if fleets_destroyed:
                fleet_losses_desc = "fleet destroyed by defenses"
            elif ships_lost or integrity_lost:
                fleet_losses_desc = f"{ships_lost} ships lost, {integrity_lost}% integrity lost"

            if fleets_destroyed:
                attacker_msg = InvasionReportMessageFactory(
                    self.game, attacker, star, False,
                    invader_colonists_kt * 1000, 0,
                    fleet_losses_desc, perspective='attacker'
                ).new_message()
                attacker_msg.year = self.game.year
                attacker_msg.save()
                if defender:
                    defender_msg = InvasionReportMessageFactory(
                        self.game, defender, star, False,
                        invader_colonists_kt * 1000, 0,
                        fleet_losses_desc, perspective='defender'
                    ).new_message()
                    defender_msg.year = self.game.year
                    defender_msg.save()
                return

        invaders = invader_colonists_kt * 1000
        defenders = star.colonists

        attacker_force = invaders * (attacker_race.ground_force_multiplier or 1.0)
        defender_force = defenders * (defender_race.ground_force_multiplier if defender_race else 1.0)

        attacker_won = attacker_force > defender_force
        if attacker_force == defender_force:
            attacker_won = False

        if attacker_won:
            remaining_invaders = int((attacker_force - defender_force) / (attacker_race.ground_force_multiplier or 1.0))
            attacker_losses = invaders - remaining_invaders
            defender_losses = defenders
            star.colonists = max(0, remaining_invaders)
            star.player = attacker
            star.save(update_fields=['colonists', 'player'])
        else:
            remaining_defenders = int((defender_force - attacker_force) / (defender_race.ground_force_multiplier if defender_race else 1.0))
            defender_losses = defenders - remaining_defenders
            attacker_losses = invaders
            star.colonists = max(0, remaining_defenders)
            star.save(update_fields=['colonists'])

        attacker_msg = InvasionReportMessageFactory(
            self.game, attacker, star, attacker_won,
            attacker_losses, defender_losses,
            fleet_losses_desc, perspective='attacker'
        ).new_message()
        attacker_msg.year = self.game.year
        attacker_msg.save()

        if defender:
            defender_msg = InvasionReportMessageFactory(
                self.game, defender, star, attacker_won,
                attacker_losses, defender_losses,
                fleet_losses_desc, perspective='defender'
            ).new_message()
            defender_msg.year = self.game.year
            defender_msg.save()

    def resolve_orbital_defense_hazards(self):
        """Resolve occasional defensive fire against hostile fleets in orbit.

        Applies only when a hostile fleet is co-located with an enemy defended colony,
        no active fleet-vs-fleet combat occurred there this step, and a luck-adjusted
        trigger roll succeeds.
        """
        from .models import Fleet, Star

        defended_stars = Star.objects.filter(
            game=self.game,
            player__isnull=False,
            defenses__gt=0,
        ).select_related('player', 'player__race_type')

        for star in defended_stars:
            defender = star.player
            if defender is None:
                continue

            hostile_fleets = Fleet.objects.filter(
                game=self.game,
                x=star.x,
                y=star.y,
            ).exclude(player=defender)

            for fleet in hostile_fleets:
                self._resolve_orbital_defense_hazard(star, fleet)

    def _resolve_orbital_defense_hazard(self, star, fleet):
        """Attempt one defensive hazard hit on a hostile fleet."""
        defender = star.player
        attacker = fleet.player
        if defender is None or attacker is None:
            return
        if fleet.integrity <= 0 or fleet.ship_count <= 0:
            return

        effective_defenses = calculate_effective_defenses(star)
        if effective_defenses <= 0:
            return

        attacker_luck = max(0.1, float(getattr(attacker.race_type, 'luck_multiplier', 1.0) or 1.0))
        defender_luck = max(0.1, float(getattr(defender.race_type, 'luck_multiplier', 1.0) or 1.0))
        chance = luck_ratio_chance(
            ORBITAL_DEFENSE_HAZARD_BASE_CHANCE,
            source_luck=defender_luck,
            target_luck=attacker_luck,
            min_chance=ORBITAL_DEFENSE_HAZARD_MIN_CHANCE,
            max_chance=ORBITAL_DEFENSE_HAZARD_MAX_CHANCE,
        )
        if not roll_chance(chance):
            return

        defender_defence_mult = float(getattr(defender.race_type, 'defence_multiplier', 1.0) or 1.0)
        colony_defense_level = get_player_colony_defense_level(defender)
        defender_defence_mult *= tech_level_to_multiplier(colony_defense_level)

        attacker_strength = calculate_fleet_strength(
            fleet,
            defender_defence_mult,
            attack_roll_scale=1.0,
        )
        defender_strength = normalize_ship_count(effective_defenses)
        strength_by_player = {
            attacker: attacker_strength,
            defender: defender_strength,
        }
        damage_taken = self._calculate_combat_damage(strength_by_player)
        hazard_damage = max(0.0, float(damage_taken.get(attacker, 0.0)) * ORBITAL_DEFENSE_HAZARD_DAMAGE_FACTOR)
        if hazard_damage <= 0:
            return

        results = self._apply_combat_damage(
            {attacker: [fleet], defender: []},
            {attacker: hazard_damage, defender: 0.0}
        )
        result = results.get(attacker, {}) or {}
        integrity_lost = int(result.get('integrity_lost', 0) or 0)
        if integrity_lost <= 0:
            return

        attacker_msg = OrbitalDefenseHitMessageFactory(
            self.game, attacker, star, fleet.name, integrity_lost, perspective='attacker'
        ).new_message()
        attacker_msg.year = self.game.year
        attacker_msg.save()

        defender_msg = OrbitalDefenseHitMessageFactory(
            self.game, defender, star, fleet.name, integrity_lost, perspective='defender'
        ).new_message()
        defender_msg.year = self.game.year
        defender_msg.save()

    def _transfer_with_star(self, fleet, order, star):
        """Execute transfer between fleet and star."""
        fleet_max_capacity = fleet.cargo_capacity  # Use fleet's actual capacity

        if order.transfer_type == 'LOAD':
            # Load from star to fleet
            # Calculate total transfer amount and proportions
            total_requested = (order.transfer_ironium + order.transfer_boranium +
                             order.transfer_germanium + order.transfer_colonists)

            if total_requested == 0:
                return

            # Limit total transfer by fleet available space
            fleet_used = fleet.cargo_used
            fleet_available = fleet_max_capacity - fleet_used
            total_transfer = min(fleet_available, total_requested)

            if total_transfer <= 0:
                return

            # Calculate proportional transfers
            transfer_factor = total_transfer / total_requested

            ironium_transfer = min(int(order.transfer_ironium * transfer_factor), star.ironium_inventory)
            boranium_transfer = min(int(order.transfer_boranium * transfer_factor), star.boranium_inventory)
            germanium_transfer = min(int(order.transfer_germanium * transfer_factor), star.germanium_inventory)
            # Convert colonists: star.colonists is individual units, fleet.colonists is thousands
            colonists_transfer_kt = int(order.transfer_colonists * transfer_factor)  # This is in kt
            colonists_transfer_individuals = min(colonists_transfer_kt * 1000, star.colonists)
            colonists_transfer_kt_actual = colonists_transfer_individuals // 1000

            # Execute the transfers
            star.ironium_inventory -= ironium_transfer
            star.boranium_inventory -= boranium_transfer
            star.germanium_inventory -= germanium_transfer
            star.colonists -= colonists_transfer_individuals

            fleet.ironium_inventory += ironium_transfer
            fleet.boranium_inventory += boranium_transfer
            fleet.germanium_inventory += germanium_transfer
            fleet.colonists += colonists_transfer_kt_actual

            star.save()
            fleet.save()

        elif order.transfer_type in ('UNLOAD', 'UNLOAD_ALL'):
            # Unload from fleet to star
            # For UNLOAD_ALL, transfer everything; for UNLOAD, use order amounts
            if order.transfer_type == 'UNLOAD_ALL':
                ironium_transfer = fleet.ironium_inventory
                boranium_transfer = fleet.boranium_inventory
                germanium_transfer = fleet.germanium_inventory
                colonists_transfer_kt = fleet.colonists
            else:
                ironium_transfer = min(order.transfer_ironium, fleet.ironium_inventory)
                boranium_transfer = min(order.transfer_boranium, fleet.boranium_inventory)
                germanium_transfer = min(order.transfer_germanium, fleet.germanium_inventory)
                colonists_transfer_kt = min(order.transfer_colonists, fleet.colonists)

            # If transferring colonists to an unowned star, allow low-chance colonisation
            if colonists_transfer_kt > 0 and star.player is None:
                if random.random() < 0.10:
                    star.player = fleet.player
                    factory = ColonistsUnexpectedColonyMessageFactory(
                        self.game, fleet.player, fleet.name, colonists_transfer_kt, star
                    )
                    msg = factory.new_message()
                    msg.year = self.game.year
                    msg.save()
                else:
                    # Colonists perish
                    fleet.colonists -= colonists_transfer_kt
                    factory = ColonistsFailedToColoniseMessageFactory(
                        self.game, fleet.player, fleet.name, colonists_transfer_kt, star
                    )
                    msg = factory.new_message()
                    msg.year = self.game.year
                    msg.save()
                    colonists_transfer_kt = 0

            # If transferring colonists to an enemy colony, trigger invasion
            if colonists_transfer_kt > 0 and star.player and star.player != fleet.player:
                self._handle_invasion(fleet, star, colonists_transfer_kt)
                # Remove colonists from fleet regardless of invasion outcome
                fleet.colonists -= colonists_transfer_kt
                # Continue with mineral transfers only
                colonists_transfer_kt = 0

            # Convert colonists: fleet.colonists is thousands, star.colonists is individual units
            colonists_transfer_individuals = colonists_transfer_kt * 1000

            # Execute the transfers
            fleet.ironium_inventory -= ironium_transfer
            fleet.boranium_inventory -= boranium_transfer
            fleet.germanium_inventory -= germanium_transfer
            fleet.colonists -= colonists_transfer_kt

            star.ironium_inventory += ironium_transfer
            star.boranium_inventory += boranium_transfer
            star.germanium_inventory += germanium_transfer
            star.colonists += colonists_transfer_individuals

            star.save()
            fleet.save()

            if (ironium_transfer or boranium_transfer or germanium_transfer) and star.player and star.player != fleet.player:
                gift_factory = MineralGiftMessageFactory(
                    self.game, star.player, fleet.name, star,
                    ironium_transfer, boranium_transfer, germanium_transfer
                )
                gift_msg = gift_factory.new_message()
                gift_msg.year = self.game.year
                gift_msg.save()

    def _transfer_with_fleet(self, source_fleet, order, target_fleet):
        """Execute transfer between two fleets.

        Both fleets store colonists in thousands (1 unit = 1000 colonists),
        so no unit conversion is needed for fleet-to-fleet transfers.
        """
        if order.transfer_type == 'LOAD':
            # Load from target fleet to source fleet
            # Calculate total transfer amount and proportions
            total_requested = (order.transfer_ironium + order.transfer_boranium +
                             order.transfer_germanium + order.transfer_colonists)

            if total_requested == 0:
                return

            # Limit total transfer by source fleet available space
            source_used = source_fleet.cargo_used
            source_available = source_fleet.cargo_capacity - source_used
            total_transfer = min(source_available, total_requested)

            if total_transfer <= 0:
                return

            # Calculate proportional transfers
            transfer_factor = total_transfer / total_requested

            ironium_transfer = min(int(order.transfer_ironium * transfer_factor), target_fleet.ironium_inventory)
            boranium_transfer = min(int(order.transfer_boranium * transfer_factor), target_fleet.boranium_inventory)
            germanium_transfer = min(int(order.transfer_germanium * transfer_factor), target_fleet.germanium_inventory)
            colonists_transfer = min(int(order.transfer_colonists * transfer_factor), target_fleet.colonists)

            # Execute the transfers (both fleets store colonists as thousands)
            target_fleet.ironium_inventory -= ironium_transfer
            target_fleet.boranium_inventory -= boranium_transfer
            target_fleet.germanium_inventory -= germanium_transfer
            target_fleet.colonists -= colonists_transfer

            source_fleet.ironium_inventory += ironium_transfer
            source_fleet.boranium_inventory += boranium_transfer
            source_fleet.germanium_inventory += germanium_transfer
            source_fleet.colonists += colonists_transfer

            target_fleet.save()
            source_fleet.save()

        else:  # UNLOAD or UNLOAD_ALL
            # Unload from source fleet to target fleet
            # For UNLOAD_ALL, transfer everything; for UNLOAD, use order amounts
            if order.transfer_type == 'UNLOAD_ALL':
                ironium_transfer = source_fleet.ironium_inventory
                boranium_transfer = source_fleet.boranium_inventory
                germanium_transfer = source_fleet.germanium_inventory
                colonists_transfer = source_fleet.colonists
            else:
                ironium_transfer = min(order.transfer_ironium, source_fleet.ironium_inventory)
                boranium_transfer = min(order.transfer_boranium, source_fleet.boranium_inventory)
                germanium_transfer = min(order.transfer_germanium, source_fleet.germanium_inventory)
                colonists_transfer = min(order.transfer_colonists, source_fleet.colonists)

            # Check if target fleet has capacity
            target_used = target_fleet.cargo_used
            target_available = target_fleet.cargo_capacity - target_used
            total_transfer = ironium_transfer + boranium_transfer + germanium_transfer + colonists_transfer

            if total_transfer > target_available:
                # Scale down transfers proportionally
                if target_available <= 0:
                    return
                scale_factor = target_available / total_transfer
                ironium_transfer = int(ironium_transfer * scale_factor)
                boranium_transfer = int(boranium_transfer * scale_factor)
                germanium_transfer = int(germanium_transfer * scale_factor)
                colonists_transfer = int(colonists_transfer * scale_factor)

            # Execute the transfers
            source_fleet.ironium_inventory -= ironium_transfer
            source_fleet.boranium_inventory -= boranium_transfer
            source_fleet.germanium_inventory -= germanium_transfer
            source_fleet.colonists -= colonists_transfer

            target_fleet.ironium_inventory += ironium_transfer
            target_fleet.boranium_inventory += boranium_transfer
            target_fleet.germanium_inventory += germanium_transfer
            target_fleet.colonists += colonists_transfer

            source_fleet.save()
            target_fleet.save()

    def _transfer_with_salvage(self, fleet, order, salvage):
        """Execute transfer from salvage to fleet (LOAD only).

        Salvage only supports LOAD - you pick up minerals from the debris.
        UNLOAD to salvage doesn't make sense and is ignored.
        """
        from .messages import SalvageCollectedMessageFactory

        # Salvage only supports LOAD operations
        if order.transfer_type not in ('LOAD',):
            return

        # Calculate how much we can load (respecting cargo capacity)
        fleet_available = fleet.cargo_remaining

        # If no specific amounts requested, load everything we can
        if (order.transfer_ironium == 0 and order.transfer_boranium == 0 and
                order.transfer_germanium == 0):
            # Load all salvage, respecting capacity
            total_salvage = salvage.total_minerals
            if total_salvage == 0:
                return

            if total_salvage <= fleet_available:
                # Take everything
                ironium_transfer = salvage.ironium_inventory
                boranium_transfer = salvage.boranium_inventory
                germanium_transfer = salvage.germanium_inventory
            else:
                # Proportional transfer
                ratio = fleet_available / total_salvage
                ironium_transfer = int(salvage.ironium_inventory * ratio)
                boranium_transfer = int(salvage.boranium_inventory * ratio)
                germanium_transfer = int(salvage.germanium_inventory * ratio)
        else:
            # Transfer requested amounts (limited by available)
            total_requested = (order.transfer_ironium + order.transfer_boranium +
                               order.transfer_germanium)
            if total_requested == 0:
                return

            # Limit by fleet available space
            total_transfer = min(fleet_available, total_requested)
            if total_transfer <= 0:
                return

            # Calculate proportional transfers
            transfer_factor = total_transfer / total_requested
            ironium_transfer = min(
                int(order.transfer_ironium * transfer_factor),
                salvage.ironium_inventory
            )
            boranium_transfer = min(
                int(order.transfer_boranium * transfer_factor),
                salvage.boranium_inventory
            )
            germanium_transfer = min(
                int(order.transfer_germanium * transfer_factor),
                salvage.germanium_inventory
            )

        # Execute the transfer
        salvage.ironium_inventory -= ironium_transfer
        salvage.boranium_inventory -= boranium_transfer
        salvage.germanium_inventory -= germanium_transfer

        fleet.ironium_inventory += ironium_transfer
        fleet.boranium_inventory += boranium_transfer
        fleet.germanium_inventory += germanium_transfer

        fleet.save()

        # Delete salvage if emptied, otherwise save
        if salvage.total_minerals == 0:
            salvage.delete()
        else:
            salvage.save()

        # Create collection message if anything was transferred
        if ironium_transfer > 0 or boranium_transfer > 0 or germanium_transfer > 0:
            factory = SalvageCollectedMessageFactory(
                self.game, fleet.player, fleet,
                ironium_transfer, boranium_transfer, germanium_transfer
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()

    def _try_execute_colonise(self, fleet, order):
        """Try to execute a colonise order.

        Colonise orders execute when the fleet is at the target star location.
        The fleet is destroyed and all cargo + bonus materials are deposited.

        Returns:
        - 'executed': Colonise completed, fleet destroyed
        - 'waiting': Waiting for fleet to reach destination
        """
        _, dest_x, dest_y, kind = order.get_actual_target()
        if kind in ['invalid', 'none']:
            return 'executed'  # Invalid order, treat as executed to remove it

        # Check if fleet is at the colonise destination
        if fleet.x != dest_x or fleet.y != dest_y:
            return 'waiting'

        # Fleet is at destination, execute colonise
        return self._execute_colonise_order(fleet, order)

    def _try_execute_bomb(self, fleet, order):
        """Try to execute a bombardment order at the targeted star."""
        _, dest_x, dest_y, kind = order.get_actual_target()
        if kind == 'none':
            order.delete()
            return 'executed'
        if fleet.x != dest_x or fleet.y != dest_y:
            return 'waiting'
        return self._execute_bomb_order(fleet, order)

    def _resolve_planetary_defense_fire_against_fleet(self, star, fleet, damage_multiplier=1.0):
        """Apply colony defense fire to a hostile fleet before bombardment."""
        if not star.player or star.player == fleet.player:
            return {'destroyed': False, 'integrity_lost': 0, 'ships_lost': 0, 'defense_mult': 1.0}

        effective_defenses = calculate_effective_defenses(star)
        if effective_defenses <= 0:
            return {'destroyed': False, 'integrity_lost': 0, 'ships_lost': 0, 'defense_mult': 1.0}

        defender = star.player
        defender_defence_mult = float(getattr(defender.race_type, 'defence_multiplier', 1.0) or 1.0)
        defender_defence_mult *= tech_level_to_multiplier(get_player_colony_defense_level(defender))

        attacker_strength = calculate_fleet_strength(fleet, defender_defence_mult)
        defender_strength = normalize_ship_count(effective_defenses)
        strength_by_player = {
            fleet.player: attacker_strength,
            defender: defender_strength,
        }
        damage_taken = self._calculate_combat_damage(strength_by_player)
        try:
            mult = float(damage_multiplier)
        except (TypeError, ValueError):
            mult = 1.0
        mult = max(0.0, mult)
        if mult != 1.0:
            damage_taken[fleet.player] = float(damage_taken.get(fleet.player, 0.0)) * mult
        results = self._apply_combat_damage(
            {fleet.player: [fleet], defender: []},
            damage_taken
        )
        result = results.get(fleet.player, {}) or {}
        return {
            'destroyed': bool(result.get('fleets_destroyed', 0)),
            'integrity_lost': int(result.get('integrity_lost', 0) or 0),
            'ships_lost': int(result.get('ships_lost', 0) or 0),
            'defense_mult': max(1.0, defender_defence_mult),
        }

    def _execute_bomb_order(self, fleet, order):
        """Execute one year of bombardment damage."""
        from .models import Star

        star = None
        if order.target_star_id:
            star = Star.objects.filter(id=order.target_star_id, game=self.game).first()
        if star is None:
            _, target_x, target_y, _ = order.get_actual_target()
            star = Star.objects.filter(game=self.game, x=target_x, y=target_y).first()

        if star is None:
            _, target_x, target_y, _ = order.get_actual_target()
            factory = BombardFailedNoStarMessageFactory(
                self.game, fleet.player, fleet.name, target_x, target_y
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()
            order.delete()
            return 'executed'

        bomb_type = normalize_bomb_type(getattr(fleet, 'has_bombs', None))
        if bomb_type is None:
            order.delete()
            return 'executed'

        defense_fire = self._resolve_planetary_defense_fire_against_fleet(star, fleet)
        if defense_fire.get('destroyed'):
            factory = FleetBombardmentReportMessageFactory(
                self.game,
                fleet.player,
                fleet=fleet,
                star_name=star.name,
                bomb_type=bomb_type,
                defenses_lost=0,
                colonists_lost=0,
                mines_lost=0,
                factories_lost=0,
                labs_lost=0,
                shipyards_lost=0,
                integrity_lost=defense_fire.get('integrity_lost', 0),
                ships_lost=defense_fire.get('ships_lost', 0),
                star_destroyed=False,
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()
            return 'fleet_destroyed'

        defending_player = star.player if star.player and star.player != fleet.player else None
        pre = {
            'defenses': int(star.defenses or 0),
            'colonists': int(star.colonists or 0),
            'mines': int(star.mines or 0),
            'factories': int(star.factories or 0),
            'labs': int(star.labs or 0),
            'shipyards': int(star.shipyards or 0),
        }
        effective_defenses = max(0.0, float(calculate_effective_defenses(star)))
        luck_multiplier = float(getattr(fleet.player.race_type, 'luck_multiplier', 1.0) or 1.0)
        damage_k = bombardment_damage_k(
            fleet.ship_count,
            fleet.offense_level,
            effective_defenses * defense_fire.get('defense_mult', 1.0),
            luck_multiplier,
            bomb_type,
        )

        defenses_lost = min(pre['defenses'], damage_k)
        colonists_lost = min(pre['colonists'], damage_k * 1000)
        star.defenses = max(0, pre['defenses'] - defenses_lost)
        star.colonists = max(0, pre['colonists'] - colonists_lost)

        mines_lost = 0
        factories_lost = 0
        labs_lost = 0
        shipyards_lost = 0
        if not smart_bombs_only_target_defenses_and_population(bomb_type):
            mines_lost = min(pre['mines'], damage_k)
            factories_lost = min(pre['factories'], damage_k)
            labs_lost = min(pre['labs'], damage_k)
            shipyards_lost = min(pre['shipyards'], damage_k)
            star.mines = max(0, pre['mines'] - mines_lost)
            star.factories = max(0, pre['factories'] - factories_lost)
            star.labs = max(0, pre['labs'] - labs_lost)
            star.shipyards = max(0, pre['shipyards'] - shipyards_lost)

        star_destroyed = False
        destroyed_star_name = star.name
        if bomb_type == 'NOVA' and roll_chance(NOVA_STAR_DESTRUCTION_CHANCE):
            star_destroyed = True
            destroyed_x = star.x
            destroyed_y = star.y
            destroyed_owner_id = star.player_id
            star.delete()
            self._notify_star_vanished(
                destroyed_star_name, destroyed_x, destroyed_y, fleet,
                former_owner_id=destroyed_owner_id
            )
        else:
            star.save(update_fields=['defenses', 'colonists', 'mines', 'factories', 'labs', 'shipyards'])

        factory = FleetBombardmentReportMessageFactory(
            self.game,
            fleet.player,
            fleet=fleet,
            star_name=destroyed_star_name,
            bomb_type=bomb_type,
            defenses_lost=defenses_lost,
            colonists_lost=colonists_lost,
            mines_lost=mines_lost,
            factories_lost=factories_lost,
            labs_lost=labs_lost,
            shipyards_lost=shipyards_lost,
            integrity_lost=defense_fire.get('integrity_lost', 0),
            ships_lost=defense_fire.get('ships_lost', 0),
            star_destroyed=star_destroyed,
        )
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

        if defending_player is not None:
            total_losses = (
                defenses_lost + colonists_lost +
                mines_lost + factories_lost + labs_lost + shipyards_lost
            )
            if total_losses > 0 or star_destroyed:
                defender_factory = FleetBombardmentReportMessageFactory(
                    self.game,
                    defending_player,
                    fleet=fleet,
                    star_name=destroyed_star_name,
                    bomb_type=bomb_type,
                    defenses_lost=defenses_lost,
                    colonists_lost=colonists_lost,
                    mines_lost=mines_lost,
                    factories_lost=factories_lost,
                    labs_lost=labs_lost,
                    shipyards_lost=shipyards_lost,
                    integrity_lost=defense_fire.get('integrity_lost', 0),
                    ships_lost=defense_fire.get('ships_lost', 0),
                    star_destroyed=star_destroyed,
                    perspective='defender',
                    attacker_fleet_name=fleet.name,
                )
                defender_msg = defender_factory.new_message()
                defender_msg.year = self.game.year
                defender_msg.save()

        completion_mode = (getattr(order, 'bomb_until', None) or 'COLONISTS_ZERO').upper()
        if completion_mode == 'CONTINUOUS':
            completion_mode = 'ONCE'
        completed = False
        if star_destroyed:
            completed = True
        elif completion_mode == 'COLONISTS_ZERO':
            # Only complete when population transitions from >0 to 0.
            completed = pre['colonists'] > 0 and int(star.colonists or 0) <= 0
        elif completion_mode == 'DEFENSES_ZERO':
            completed = pre['defenses'] > 0 and int(star.defenses or 0) <= 0
        elif completion_mode == 'ONCE':
            completed = True
        else:
            completed = pre['colonists'] > 0 and int(star.colonists or 0) <= 0

        if completed:
            if order.repeat:
                self._handle_repeating_order(order)
            order.delete()
            return 'executed'
        return 'blocked'

    def _notify_star_vanished(self, star_name, x, y, attacking_fleet, former_owner_id=None):
        """Send ominous notifications when a star disappears."""
        for player in self.game.players.all():
            mention_fleet = random.random() < STAR_VANISH_FLEET_MENTION_CHANCE
            factory = StarVanishedOminousMessageFactory(
                self.game,
                player,
                star_name=star_name,
                x=x,
                y=y,
                fleet_name=attacking_fleet.name if mention_fleet else None,
                priority=(former_owner_id is not None and player.id == former_owner_id),
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()

    def _try_execute_remote_mine(self, fleet, order):
        """Try to execute a remote mining order at the targeted star."""
        _, dest_x, dest_y, kind = order.get_actual_target()
        if kind == 'none':
            order.delete()
            return 'executed'
        if fleet.x != dest_x or fleet.y != dest_y:
            return 'waiting'
        return self._execute_remote_mine_order(fleet, order)

    def _extract_minerals_with_standard_rules(self, star, total_extraction):
        """Extract minerals from a star using standard mining/depletion mechanics.

        Returns per-resource extracted whole kt:
        {'ironium': int, 'boranium': int, 'germanium': int}
        and updates star yield fields in-place.
        """
        total_extraction = max(0.0, float(total_extraction or 0.0))
        if total_extraction <= 0:
            return {'ironium': 0, 'boranium': 0, 'germanium': 0}

        total_yield = int(star.ironium_yield or 0) + int(star.boranium_yield or 0) + int(star.germanium_yield or 0)
        if total_yield <= 0:
            return {'ironium': 0, 'boranium': 0, 'germanium': 0}

        is_homeworld = star.homeworld_of.exists()
        min_yield = HOMEWORLD_MIN_YIELD if is_homeworld else 0
        produced = {'ironium': 0, 'boranium': 0, 'germanium': 0}

        for resource in ['ironium_yield', 'boranium_yield', 'germanium_yield']:
            yield_val = int(getattr(star, resource) or 0)
            if yield_val <= 0:
                continue

            extraction = total_extraction * yield_val / total_yield
            whole_kt = int(extraction)
            fractional = extraction - whole_kt
            if fractional > 0 and random.random() < fractional:
                whole_kt += 1

            resource_key = resource.replace('_yield', '')
            produced[resource_key] = whole_kt

            if whole_kt <= 0:
                continue

            sustainable_extraction = max(1.0, float(yield_val))
            overmining_ratio = max(
                0.0,
                (float(extraction) - sustainable_extraction) / sustainable_extraction
            )
            depletion_rate = (
                YIELD_DEPLETION_RATE * (
                    1.0 + (overmining_ratio * OVERMINING_DEPLETION_MULTIPLIER)
                )
            )
            depletion = whole_kt * depletion_rate
            whole_depletion = int(depletion)
            depletion_fraction = depletion - whole_depletion
            if depletion_fraction > 0 and random.random() < depletion_fraction:
                whole_depletion += 1
            if whole_depletion > 0:
                new_yield = max(min_yield, yield_val - whole_depletion)
                setattr(star, resource, new_yield)

        return produced

    def _execute_remote_mine_order(self, fleet, order):
        """Execute one year of remote mining into fleet cargo with surface overflow."""
        from .models import Star

        star = None
        if order.target_star_id:
            star = Star.objects.filter(id=order.target_star_id, game=self.game).first()
        if star is None:
            _, target_x, target_y, _ = order.get_actual_target()
            star = Star.objects.filter(game=self.game, x=target_x, y=target_y).first()
        if star is None:
            order.delete()
            return 'executed'

        miner_type = normalize_miner_type(getattr(fleet, 'has_miners', None))
        miner_units_per_ship = REMOTE_MINER_UNITS_BY_TYPE.get(miner_type, 0)
        if miner_units_per_ship <= 0:
            order.delete()
            return 'executed'
        mine_until_full = bool(getattr(order, 'mine_until_full', True))
        if int(fleet.cargo_remaining or 0) <= 0:
            if order.repeat:
                self._handle_repeating_order(order)
            order.delete()
            return 'executed'

        if star.player and star.player != fleet.player:
            defense_fire = self._resolve_planetary_defense_fire_against_fleet(
                star,
                fleet,
                damage_multiplier=REMOTE_MINE_DEFENSE_DAMAGE_MULTIPLIER,
            )
            if defense_fire.get('destroyed'):
                return 'fleet_destroyed'
            if roll_chance(REMOTE_MINE_HARASS_CHANCE):
                effective_defenses = max(0.0, float(calculate_effective_defenses(star)))
                luck_multiplier = float(getattr(fleet.player.race_type, 'luck_multiplier', 1.0) or 1.0)
                conventional_damage = bombardment_damage_k(
                    fleet.ship_count,
                    fleet.offense_level,
                    effective_defenses * defense_fire.get('defense_mult', 1.0),
                    luck_multiplier,
                    'CONVENTIONAL',
                )
                harass_damage = max(0, int(conventional_damage * REMOTE_MINE_HARASS_DAMAGE_FACTOR))
                if harass_damage > 0:
                    defenses_lost = min(int(star.defenses or 0), harass_damage)
                    colonists_lost = min(int(star.colonists or 0), harass_damage * 1000)
                    mines_lost = min(int(star.mines or 0), harass_damage)
                    factories_lost = min(int(star.factories or 0), harass_damage)
                    labs_lost = min(int(star.labs or 0), harass_damage)
                    shipyards_lost = min(int(star.shipyards or 0), harass_damage)
                    star.defenses = max(0, int(star.defenses or 0) - defenses_lost)
                    star.colonists = max(0, int(star.colonists or 0) - colonists_lost)
                    star.mines = max(0, int(star.mines or 0) - mines_lost)
                    star.factories = max(0, int(star.factories or 0) - factories_lost)
                    star.labs = max(0, int(star.labs or 0) - labs_lost)
                    star.shipyards = max(0, int(star.shipyards or 0) - shipyards_lost)

        virtual_mines = max(0, int(fleet.ship_count or 0)) * miner_units_per_ship
        total_extraction = float(virtual_mines) * KT_PER_MINE
        produced = self._extract_minerals_with_standard_rules(star, total_extraction)

        remaining_capacity = max(0, int(fleet.cargo_remaining or 0))
        fleet_iron = min(produced['ironium'], remaining_capacity)
        remaining_capacity -= fleet_iron
        fleet_bor = min(produced['boranium'], remaining_capacity)
        remaining_capacity -= fleet_bor
        fleet_germ = min(produced['germanium'], remaining_capacity)

        surface_iron = produced['ironium'] - fleet_iron
        surface_bor = produced['boranium'] - fleet_bor
        surface_germ = produced['germanium'] - fleet_germ

        fleet.ironium_inventory += fleet_iron
        fleet.boranium_inventory += fleet_bor
        fleet.germanium_inventory += fleet_germ
        star.ironium_inventory += surface_iron
        star.boranium_inventory += surface_bor
        star.germanium_inventory += surface_germ

        fleet.save(update_fields=['ironium_inventory', 'boranium_inventory', 'germanium_inventory'])
        star.save(update_fields=[
            'ironium_inventory', 'boranium_inventory', 'germanium_inventory',
            'defenses', 'colonists', 'mines', 'factories', 'labs', 'shipyards',
            'ironium_yield', 'boranium_yield', 'germanium_yield',
        ])

        if mine_until_full and int(fleet.cargo_remaining or 0) > 0:
            return 'blocked'

        if order.repeat:
            self._handle_repeating_order(order)
        order.delete()
        return 'executed'

    def _execute_colonise_order(self, fleet, order):
        """Execute a colonise order: transfer cargo, add bonus materials, delete fleet.

        This operation is atomic - either all changes succeed or none do.
        Returns 'executed' on success.
        """
        from .models import Star
        from django.db import transaction

        # Get the target star
        star = None
        if order.target_star:
            star = order.target_star
        else:
            # Look for star at the fleet's location
            _, dest_x, dest_y, _ = order.get_actual_target()
            star = Star.objects.filter(game=self.game, x=dest_x, y=dest_y).first()

        if not star:
            # No star at location, cannot colonise - create message and delete order
            _, dest_x, dest_y, _ = order.get_actual_target()
            factory = ColoniseFailedNoStarMessageFactory(
                self.game, fleet.player, fleet.name, dest_x, dest_y,
                target_star=order.target_star  # May be None if order used coordinates
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()
            order.delete()
            return 'executed'

        # Check if star is already owned
        if star.player is not None:
            factory = ColoniseFailedAlreadyOwnedMessageFactory(
                self.game,
                fleet.player,
                fleet.name,
                star,
                same_player=(star.player == fleet.player)
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()
            order.delete()
            return 'executed'

        # Check if fleet has colonists - can't colonise without them
        if fleet.colonists <= 0:
            factory = ColoniseFailedNoColonistsMessageFactory(
                self.game, fleet.player, fleet.name, star
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()
            order.delete()
            return 'executed'

        # Store values before fleet is deleted
        fleet_name = fleet.name
        player = fleet.player
        ironium = fleet.ironium_inventory
        boranium = fleet.boranium_inventory
        germanium = fleet.germanium_inventory
        colonists_kt = fleet.colonists
        dry_mass = fleet.dry_mass

        # Calculate bonus materials upfront
        bonus_ironium = random.randint(0, dry_mass)
        remaining = dry_mass - bonus_ironium
        bonus_boranium = random.randint(0, remaining)
        bonus_germanium = remaining - bonus_boranium
        total_bonus = bonus_ironium + bonus_boranium + bonus_germanium

        # Build cargo summary including bonus materials (before transaction)
        total_ironium = ironium + bonus_ironium
        total_boranium = boranium + bonus_boranium
        total_germanium = germanium + bonus_germanium
        cargo_parts = []
        if total_ironium > 0:
            cargo_parts.append(f"{total_ironium}kt Ironium")
        if total_boranium > 0:
            cargo_parts.append(f"{total_boranium}kt Boranium")
        if total_germanium > 0:
            cargo_parts.append(f"{total_germanium}kt Germanium")
        if colonists_kt > 0:
            cargo_parts.append(f"{colonists_kt}k colonists")
        if len(cargo_parts) > 1:
            cargo_summary = ", ".join(cargo_parts[:-1]) + ", and " + cargo_parts[-1]
        elif cargo_parts:
            cargo_summary = cargo_parts[0]
        else:
            cargo_summary = "no cargo"

        # Execute all database changes atomically
        with transaction.atomic():
            # Delete the fleet first (this removes the source of materials)
            order.delete()
            fleet.delete()

            # Now add materials to star (fleet is gone, no duplication possible)
            star.ironium_inventory += ironium + bonus_ironium
            star.boranium_inventory += boranium + bonus_boranium
            star.germanium_inventory += germanium + bonus_germanium
            star.colonists += colonists_kt * 1000  # Convert thousands to individuals

            # Set ownership of the star
            star.player = player
            star.save()

            # Create message for player
            factory = FleetColonisedMessageFactory(
                self.game, player, fleet_name, star, cargo_summary
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()

        return 'executed'

    def _execute_merge_order(self, source_fleet, order):
        """Execute a merge order, combining source fleet into target fleet.

        Returns:
        - 'executed': Merge completed, source fleet deleted
        - 'waiting': Fleets not at same location yet
        - 'invalid': Target fleet invalid or belongs to different player
        """
        from .models import FleetOrders

        target_fleet = order.target_fleet

        # Validate target exists and belongs to same player
        if not target_fleet or target_fleet.player != source_fleet.player:
            order.delete()
            return 'invalid'

        # Check both fleets at same location
        if source_fleet.x != target_fleet.x or source_fleet.y != target_fleet.y:
            return 'waiting'

        # Store source name before deletion for message
        source_name = source_fleet.name
        player = source_fleet.player

        # Calculate weighted average integrity
        total_ships = source_fleet.ship_count + target_fleet.ship_count
        avg_integrity = (
            (source_fleet.integrity * source_fleet.ship_count) +
            (target_fleet.integrity * target_fleet.ship_count)
        ) // total_ships
        source_attack_mult = tech_level_to_multiplier(source_fleet.offense_level)
        target_attack_mult = tech_level_to_multiplier(target_fleet.offense_level)
        merged_count_norm = normalize_ship_count(total_ships)
        source_count_norm = normalize_ship_count(source_fleet.ship_count)
        target_count_norm = normalize_ship_count(target_fleet.ship_count)

        # Preserve proportional pre-merge attack contribution with a slight
        # retention penalty so merging remains a strategic tradeoff.
        combined_attack_score = (
            (source_count_norm * source_attack_mult) +
            (target_count_norm * target_attack_mult)
        ) * MERGE_COMBAT_RETENTION
        merged_attack_mult = combined_attack_score / max(0.001, merged_count_norm)

        source_defense_mult = tech_level_to_multiplier(source_fleet.defense_level)
        target_defense_mult = tech_level_to_multiplier(target_fleet.defense_level)
        combined_defense_score = (
            (source_defense_mult * source_fleet.ship_count) +
            (target_defense_mult * target_fleet.ship_count)
        ) * MERGE_COMBAT_RETENTION
        merged_defense_mult = combined_defense_score / float(total_ships)

        merged_offense_level = multiplier_to_tech_level(merged_attack_mult)
        merged_defense_level = multiplier_to_tech_level(merged_defense_mult)
        weighted_fuel_efficiency = (
            (source_fleet.fuel_efficiency * source_fleet.ship_count) +
            (target_fleet.fuel_efficiency * target_fleet.ship_count)
        ) / float(total_ships)
        weighted_overmax_fuel_penalty = (
            (source_fleet.overmax_fuel_penalty * source_fleet.ship_count) +
            (target_fleet.overmax_fuel_penalty * target_fleet.ship_count)
        ) / float(total_ships)

        # Merge attributes into target fleet
        target_fleet.ship_count = total_ships
        target_fleet.cargo_capacity += source_fleet.cargo_capacity
        target_fleet.max_fuel += source_fleet.max_fuel
        target_fleet.fuel += source_fleet.fuel
        target_fleet.dry_mass += source_fleet.dry_mass
        target_fleet.max_safe_warp = min(
            target_fleet.max_safe_warp, source_fleet.max_safe_warp
        )
        target_fleet.fuel_efficiency = weighted_fuel_efficiency
        target_fleet.overmax_fuel_penalty = weighted_overmax_fuel_penalty
        target_fleet.offense_level = merged_offense_level
        target_fleet.defense_level = merged_defense_level
        target_fleet.integrity = avg_integrity
        source_bomb = normalize_bomb_type(source_fleet.has_bombs)
        target_bomb = normalize_bomb_type(target_fleet.has_bombs)
        bomb_priority = {'CONVENTIONAL': 1, 'SMART': 2, 'NOVA': 3}
        if bomb_priority.get(source_bomb, 0) > bomb_priority.get(target_bomb, 0):
            target_fleet.has_bombs = source_bomb

        source_miner = str(source_fleet.has_miners or '').strip().upper() or None
        target_miner = str(target_fleet.has_miners or '').strip().upper() or None
        miner_priority = {'SMALL': 1, 'MEDIUM': 2, 'LARGE': 3}
        if miner_priority.get(source_miner, 0) > miner_priority.get(target_miner, 0):
            target_fleet.has_miners = source_miner
        target_fleet.has_fuel_factory = bool(
            source_fleet.has_fuel_factory or target_fleet.has_fuel_factory
        )
        target_fleet.has_wormhole_drive = bool(
            source_fleet.has_wormhole_drive or target_fleet.has_wormhole_drive
        )

        # Transfer cargo (may exceed capacity - intentional for merge)
        target_fleet.ironium_inventory += source_fleet.ironium_inventory
        target_fleet.boranium_inventory += source_fleet.boranium_inventory
        target_fleet.germanium_inventory += source_fleet.germanium_inventory
        target_fleet.colonists += source_fleet.colonists

        target_fleet.save()

        # Update orders from other fleets that target the source fleet
        # Use explicit ID to avoid any object reference issues with CASCADE
        FleetOrders.objects.filter(target_fleet_id=source_fleet.id).update(
            target_fleet_id=target_fleet.id
        )

        # Delete source fleet (cascades its orders)
        source_fleet.delete()

        # Create message
        factory = FleetMergedMessageFactory(
            self.game, player, source_name, target_fleet
        )
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

        return 'executed'

    def _execute_scuttle_order(self, fleet, order):
        """Execute a scuttle order, destroying the fleet with salvage chance.

        Returns 'executed' always (fleet is deleted).
        """
        from .messages import FleetScuttledMessageFactory

        # Store fleet data before deletion
        fleet_name = fleet.name
        player = fleet.player
        x, y = fleet.x, fleet.y

        salvage_created = False
        salvage_location = None

        # 33% chance of salvage from scuttling
        if roll_chance(SALVAGE_CHANCE_SCUTTLE):
            salvage_result = self._create_salvage_from_fleet(fleet)
            if salvage_result:
                salvage_created = True
                salvage_location = salvage_result

        # Delete order and fleet
        order.delete()
        fleet.delete()

        # Create message
        factory = FleetScuttledMessageFactory(
            self.game, player, fleet_name, x, y,
            salvage_created, salvage_location
        )
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

        return 'executed'

    def _execute_patrol_order(self, fleet, order):
        """Execute a patrol order by converting it to MOVE or INTERCEPT.

        If repeat is enabled, a new patrol order is appended to the queue.
        """
        target_x, target_y = self._get_patrol_target_coordinates(order)
        enemy_fleet = self._find_patrol_enemy(
            fleet.player, target_x, target_y, order.patrol_radius, order.target_fleet
        )

        if order.repeat:
            self._append_patrol_repeat(order, fleet)
            order.repeat = False

        if enemy_fleet:
            order.order_type = 'INTERCEPT'
            order.target_fleet = enemy_fleet
            order.warpfactor = order.intercept_speed
            order.save(update_fields=['order_type', 'target_fleet', 'warpfactor', 'repeat'])
        else:
            order.order_type = 'MOVE'
            order.warpfactor = fleet.max_safe_warp
            order.target_fleet = None
            order.target_salvage = None
            order.target_star = None
            order.x = target_x
            order.y = target_y
            order.save(update_fields=[
                'order_type', 'warpfactor', 'target_fleet', 'target_salvage',
                'target_star', 'x', 'y', 'repeat'
            ])

        move_result = self._move_toward_destination(fleet, order)
        if move_result == 'destroyed':
            return 'executed'
        if move_result is True:
            order.delete()
            return 'moved'
        return 'blocked'

    def _append_patrol_repeat(self, order, fleet):
        """Append a repeat patrol order to the end of the queue."""
        from .models import FleetOrders
        FleetOrders.objects.create(
            game=self.game,
            fleet=fleet,
            order_type='PATROL',
            repeat=True,
            patrol_radius=order.patrol_radius,
            intercept_speed=order.intercept_speed,
            x=order.x,
            y=order.y,
            target_star_id=order.target_star_id,
            target_fleet_id=order.target_fleet_id,
            target_salvage_id=order.target_salvage_id,
        )

    def _get_patrol_target_coordinates(self, order):
        """Get patrol center coordinates from order target."""
        _, x, y, kind = order.get_actual_target()
        if kind in ['invalid', 'none']:
            return order.fleet.x, order.fleet.y
        return x, y

    def _find_enemy_fleet_in_radius(self, player, x, y, radius):
        """Find nearest enemy fleet within radius of a point."""
        from .models import Fleet
        if radius <= 0:
            return None

        candidates = Fleet.objects.filter(
            game=self.game
        ).exclude(player=player)

        nearest = None
        nearest_dist = None
        for enemy in candidates:
            dx = enemy.x - x
            dy = enemy.y - y
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= radius and (nearest_dist is None or dist < nearest_dist):
                nearest = enemy
                nearest_dist = dist
        return nearest

    def _find_patrol_enemy(self, player, x, y, radius, patrol_target_fleet):
        """Prefer enemy fleets other than the patrol target, if possible."""
        if patrol_target_fleet and patrol_target_fleet.player != player:
            enemy = self._find_enemy_fleet_in_radius(
                player, x, y, radius,
            )
            if enemy and enemy.id != patrol_target_fleet.id:
                return enemy
            return patrol_target_fleet

        enemy = self._find_enemy_fleet_in_radius(player, x, y, radius)
        if enemy and patrol_target_fleet and enemy.id == patrol_target_fleet.id:
            return None
        return enemy

    def population_growth(self):
        """Apply population growth/decline to all colonized planets."""
        for star in self.game.stars.filter(colonists__gt=0, player__isnull=False):
            player = star.player
            old_pop = star.colonists
            hab_factor = calculate_habitability_factor(player, star)

            factor = calculate_growth_factor(player, star)
            factor *= player.race_type.population_growth_multiplier
            star.colonists = apply_population_change(star.colonists, factor)
            change = star.colonists - old_pop

            if change < 0 and star.colonists > 0:
                cap = effective_capacity(player, star)
                if old_pop > cap:
                    # Deaths due to overcrowding
                    self._create_overcrowding_death_message(player, star, -change)
                elif hab_factor < 0:
                    # Environmental deaths - uninhabitable world
                    self._create_environmental_death_message(player, star, -change)
                else:
                    # Fallback: classify remaining decline as environmental stress.
                    self._create_environmental_death_message(player, star, -change)

            star.save()

    def _create_environmental_death_message(self, player, star, deaths):
        """Create a message for colonist deaths due to environment."""
        factory = EnvironmentalDeathMessageFactory(self.game, player, star, deaths)
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def _create_overcrowding_death_message(self, player, star, deaths):
        """Create a message for colonist deaths due to overcrowding."""
        factory = OvercrowdingDeathMessageFactory(self.game, player, star, deaths)
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def clear_empty_planets(self):
        """Remove ownership from planets with zero population."""
        # Find stars that will be abandoned and notify their owners
        for star in self.game.stars.filter(colonists=0, player__isnull=False):
            self._create_colony_abandoned_message(star.player, star)
            star.production_orders.all().delete()
            star.player = None
            star.save()

    def _create_colony_abandoned_message(self, player, star):
        """Create a message for a colony being abandoned."""
        factory = ColonyAbandonedMessageFactory(self.game, player, star)
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def check_join_deadline(self):
        """Close joining if past the deadline year."""
        if self.game.join_until_year and self.game.year >= self.game.join_until_year:
            self.game.joinable = False

    def mining(self):
        """Process mining for all colonized planets with mines.

        Each mine extracts KT_PER_MINE kt of minerals per turn,
        distributed proportionally based on yield percentages.
        Fractional amounts (<1kt) have a random chance to produce 1kt.
        Yields slowly deplete over time (homeworld minimum 30%).
        """
        from .models import Star
        for star in Star.objects.filter(game=self.game, player__isnull=False, mines__gt=0):
            total_yield = star.ironium_yield + star.boranium_yield + star.germanium_yield
            if total_yield == 0:
                continue

            staffing_ratio = calculate_staffing_ratio(star)
            if staffing_ratio == 0:
                continue
            productivity = calculate_productivity_multiplier(staffing_ratio)
            total_extraction = star.mines * KT_PER_MINE * productivity

            produced = self._extract_minerals_with_standard_rules(star, total_extraction)
            star.ironium_inventory += produced['ironium']
            star.boranium_inventory += produced['boranium']
            star.germanium_inventory += produced['germanium']

            star.save()

    def production(self):
        """Process production orders for all colonized planets.

        For each star:
        1. Reset buildpoints_consumed and colonists_busy to 0
        2. Calculate available buildpoints from factories
        3. Process orders in position order
        4. For each item: consume resources FIRST, then BP
        5. Colonists are required for mines/factories (not consumed, just busy)
        6. Continue until blocked on resources, BP, or colonists
        7. Send aggregate messages for mines/factories/defenses (4+ items)
        8. Repair damaged fleets using available shipyards
        """
        from .models import Star, ProductionOrder, PRODUCTION_COSTS
        for star in Star.objects.filter(game=self.game, player__isnull=False):
            had_production_orders = star.production_orders.exists()
            star.buildpoints_consumed = 0
            colonists_busy = 0  # Track colonists busy with construction this turn
            available_bp = calculate_available_buildpoints(star)
            blocked = False
            fleets_built_this_turn = 0  # Track fleets built for shipyard availability
            shipyard_blocked_message_sent = False  # Only send once per star

            # Track production counts for aggregate messages
            production_counts = {
                'mine': 0, 'factory': 0, 'lab': 0, 'defense': 0, 'shipyard': 0
            }

            for order in list(star.production_orders.order_by('position')):
                if blocked:
                    break

                cost = PRODUCTION_COSTS.get(order.order_type, {})

                # Check shipyard requirement for BUILD_FLEET
                if order.order_type == 'BUILD_FLEET' and star.shipyards == 0:
                    # No shipyard - block and send message (once per star)
                    if not shipyard_blocked_message_sent:
                        factory = FleetBuildBlockedNoShipyardMessageFactory(
                            self.game, star.player, star
                        )
                        msg = factory.new_message()
                        msg.year = self.game.year
                        msg.save()
                        shipyard_blocked_message_sent = True
                    blocked = True
                    break

                # Build items until we've completed the quantity or get blocked
                while order.completed < order.quantity and not blocked:
                    # Phase 1: Check colonist availability (for mines/factories)
                    colonist_cost = cost.get('colonists', 0)
                    if colonist_cost > 0:
                        available_colonists = star.colonists - colonists_busy
                        if available_colonists < colonist_cost:
                            # Blocked on colonists - save and stop
                            blocked = True
                            order.save()
                            break

                    # Phase 2: Consume resources (must complete before BP)
                    for resource in ['ironium', 'boranium', 'germanium']:
                        resource_cost = cost.get(resource, 0)
                        spent_field = f'spent_{resource}'
                        inventory_field = f'{resource}_inventory'

                        already_spent = getattr(order, spent_field)
                        needed = resource_cost - already_spent

                        if needed > 0:
                            available = getattr(star, inventory_field)
                            spend = min(needed, available)
                            setattr(order, spent_field, already_spent + spend)
                            setattr(star, inventory_field, available - spend)

                    # Check if all resources satisfied
                    resources_satisfied = all(
                        getattr(order, f'spent_{resource}') >= cost.get(resource, 0)
                        for resource in ['ironium', 'boranium', 'germanium']
                    )

                    if not resources_satisfied:
                        # Blocked on resources - save and stop
                        blocked = True
                        order.save()
                        break

                    # Phase 3: Consume BP (only after resources satisfied)
                    bp_cost = cost.get('bp', 0)
                    bp_needed = bp_cost - order.spent_bp

                    if bp_needed > 0:
                        bp_spend = min(bp_needed, available_bp)
                        order.spent_bp += bp_spend
                        available_bp -= bp_spend
                        star.buildpoints_consumed += bp_spend

                        if order.spent_bp < bp_cost:
                            # Blocked on BP - save and stop
                            blocked = True
                            order.save()
                            break

                    # Item complete! Mark colonists as busy (not consumed)
                    if colonist_cost > 0:
                        colonists_busy += colonist_cost

                    fleet_built = self._apply_production_effect(
                        star, order, production_counts
                    )
                    if fleet_built:
                        fleets_built_this_turn += 1
                    order.completed += 1
                    # Reset spent amounts for next item
                    order.spent_ironium = 0
                    order.spent_boranium = 0
                    order.spent_germanium = 0
                    order.spent_bp = 0

                # After while loop, check if order is fully complete
                if order.completed >= order.quantity:
                    if order.repeat:
                        # Requeue at bottom with fresh quantity
                        max_pos = star.production_orders.aggregate(
                            max_pos=models.Max('position'))['max_pos'] or 0
                        ProductionOrder.objects.create(
                            game=self.game,
                            star=star,
                            order_type=order.order_type,
                            position=max_pos + 1,
                            repeat=True,
                            quantity=order.quantity,
                        )
                    order.delete()
                elif not blocked:
                    order.save()

            # Send aggregate production messages (only for 4+ items)
            self._send_production_summary_messages(star, production_counts)
            self._send_production_orders_completed_message(star, had_production_orders)

            star.save()

            # Repair damaged fleets using available shipyards
            available_shipyards = star.shipyards - fleets_built_this_turn
            self._repair_fleets_at_star(star, available_shipyards)

    def _apply_production_effect(self, star, order, production_counts):
        """Apply the effect of a completed production order.

        Returns True if a fleet was built (for shipyard availability tracking).
        """
        if order.order_type == 'BUILD_FLEET':
            self._build_fleet(star, order)
            return True
        elif order.order_type == 'BUILD_MINE':
            self._build_mine(star)
            production_counts['mine'] += 1
        elif order.order_type == 'BUILD_FACTORY':
            self._build_factory(star)
            production_counts['factory'] += 1
        elif order.order_type == 'BUILD_LAB':
            self._build_lab(star)
            production_counts['lab'] += 1
        elif order.order_type == 'BUILD_DEFENSE':
            self._build_defense(star)
            production_counts['defense'] += 1
        elif order.order_type == 'BUILD_SHIPYARD':
            self._build_shipyard(star)
            production_counts['shipyard'] += 1
        elif order.order_type.startswith('TERRAFORM_'):
            self._apply_terraform_order(star, order)
        return False

    def _build_fleet(self, star, order):
        """Build a fleet at the given star and create notification."""
        from .models import Fleet
        player = star.player

        # Auto-generate fleet name
        fleet_count = player.fleets.count() + 1
        fleet_name = f"{player.name} Fleet {fleet_count}"

        tech_effects = get_player_tech_effects(player)
        thumbnail_path = choose_fleet_thumbnail(
            f"{self.game.id}:{star.id}:{fleet_name}:{self.game.year}",
            tech_effects.get('hull_thumbnail_class'),
        )
        fleet = Fleet.objects.create(
            game=self.game,
            player=player,
            name=fleet_name,
            x=star.x,
            y=star.y,
            cargo_capacity=tech_effects.get('max_cargo_capacity', 100),
            fuel=tech_effects.get('max_fuel', 50.0),
            max_fuel=tech_effects.get('max_fuel', 50.0),
            max_safe_warp=tech_effects['max_warp_speed'],
            fuel_efficiency=tech_effects.get('fuel_efficiency', 1.0),
            overmax_fuel_penalty=tech_effects.get('overmax_fuel_penalty', 1.0),
            offense_level=tech_effects['offense_level'],
            defense_level=tech_effects['defense_level'],
            has_bombs=tech_effects.get('has_bombs'),
            has_miners=tech_effects.get('has_miners'),
            has_fuel_factory=bool(tech_effects.get('has_fuel_factory')),
            has_wormhole_drive=bool(tech_effects.get('has_wormhole_drive')),
            thumbnail_path=thumbnail_path,
        )

        # Create notification message
        factory = FleetBuiltMessageFactory(self.game, player, star, fleet)
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def _build_mine(self, star):
        """Build a mine at the given star."""
        star.mines += 1

    def _build_factory(self, star):
        """Build a factory at the given star."""
        star.factories += 1

    def _build_lab(self, star):
        """Build a lab at the given star."""
        star.labs += 1

    def _build_defense(self, star):
        """Build a defense at the given star."""
        star.defenses += 1

    def _build_shipyard(self, star):
        """Build a shipyard at the given star."""
        star.shipyards += 1

    def _send_production_summary_messages(self, star, production_counts):
        """Send one construction rollup message per star per year."""
        player = star.player
        completed = {
            key: int(production_counts.get(key) or 0)
            for key in ('mine', 'factory', 'lab', 'defense', 'shipyard')
            if int(production_counts.get(key) or 0) > 0
        }
        if not completed:
            return
        factory = ProductionSummaryMessageFactory(
            self.game, player, star, completed
        )
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def _send_production_orders_completed_message(self, star, had_production_orders):
        """Send one message when a colony's production queue becomes empty."""
        if not had_production_orders:
            return
        if star.production_orders.exists():
            return
        factory = ProductionOrdersCompletedMessageFactory(self.game, star.player, star)
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def _apply_terraform_order(self, star, order):
        """Apply a single terraforming order.

        Each turn moves 1% of the remaining distance toward the player's ideal.
        This produces exponential decay that never quite reaches perfection.
        Modifies the environmental value directly.
        """
        TERRAFORM_RATE = 0.01  # 1% of remaining distance per turn

        env_map = {
            'TERRAFORM_GRAVITY': ('gravity', star.player.gravity_center),
            'TERRAFORM_TEMPERATURE': ('temperature', star.player.temperature_center),
            'TERRAFORM_RADIATION': ('radiation', star.player.radiation_center),
        }

        if order.order_type not in env_map:
            return

        field, target = env_map[order.order_type]
        current = getattr(star, field)

        # Move 1% of the way from current to target
        distance = target - current
        new_value = current + distance * TERRAFORM_RATE

        # Clamp to valid range
        new_value = max(0.0, min(2.0, new_value))

        setattr(star, field, new_value)
        star.save()

    def _repair_fleets_at_star(self, star, available_shipyards):
        """Repair damaged fleets orbiting a star using available shipyards.

        Each available shipyard repairs one ship's share of integrity per year.
        Repair is distributed across all damaged friendly fleets at the location.
        """
        from .models import Fleet

        if available_shipyards <= 0:
            return

        # Find player's damaged fleets at star location
        damaged_fleets = Fleet.objects.filter(
            game=self.game,
            player=star.player,
            x=star.x,
            y=star.y,
            integrity__lt=100
        )

        if not damaged_fleets.exists():
            return

        # Calculate total ships needing repair
        total_damaged_ships = sum(f.ship_count for f in damaged_fleets)
        if total_damaged_ships == 0:
            return

        # Each shipyard can repair one ship's worth of integrity per turn
        repair_pool = available_shipyards  # Number of "ship repairs" available

        for fleet in damaged_fleets:
            if repair_pool <= 0:
                break

            # Calculate fleet's share of repairs based on ship count
            fleet_repair_share = min(fleet.ship_count, repair_pool)
            repair_pool -= fleet_repair_share

            # Each ship repaired restores (100 / ship_count)% integrity
            # E.g., 5-ship fleet with 1 shipyard = 20% integrity restored
            integrity_gain = (fleet_repair_share * 100) // fleet.ship_count
            # Cap at missing integrity (can't repair past 100%)
            integrity_gain = min(integrity_gain, 100 - fleet.integrity)

            if integrity_gain > 0:
                old_integrity = fleet.integrity
                fleet.integrity = min(100, fleet.integrity + integrity_gain)
                fleet.save()

                # Create repair message
                factory = FleetRepairedMessageFactory(
                    self.game, star.player, fleet,
                    old_integrity, fleet.integrity, star
                )
                msg = factory.new_message()
                msg.year = self.game.year
                msg.save()

    def research(self):
        """Process one year of research progression for each player."""
        for player in self.game.players.all():
            unlocks = process_player_research_for_year(player) or []
            self._create_research_unlock_messages(player, unlocks)
            if self.game.random_events:
                self._trigger_research_breakthrough_event(player)

    def _create_research_unlock_messages(self, player, unlocks):
        """Emit messages for research levels unlocked this year."""
        for unlock in unlocks:
            factory = ResearchLevelUnlockedMessageFactory(
                self.game,
                player,
                unlock['category'].name,
                unlock['new_level'],
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()

    def _roll_research_breakthrough_rp(self):
        """Return a skewed RP bonus in the 10-300 range."""
        power = 2 if random.random() < 0.5 else 3
        skew = random.random() ** power
        return 10 + int(skew * 290)

    def _trigger_research_breakthrough_event(self, player):
        """Apply an occasional research breakthrough from a lab colony."""
        if random.random() >= RESEARCH_BREAKTHROUGH_CHANCE:
            return
        lab_stars = list(player.stars.filter(colonists__gt=0, labs__gt=0))
        if not lab_stars:
            return
        research_rows = list(player.research_progress.select_related('category'))
        if not research_rows:
            return

        star = random.choice(lab_stars)
        row = random.choice(research_rows)
        bonus_rp = self._roll_research_breakthrough_rp()
        result = apply_research_bonus_rp(player, row.category_id, bonus_rp)
        if not result:
            return

        factory = ResearchBreakthroughMessageFactory(
            self.game, player, star, row.category.name, bonus_rp
        )
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

        if result['new_level'] > result['old_level']:
            self._create_research_unlock_messages(player, [result])

    def random_events(self):
        """Process random events for colonized planets."""
        if not self.game.random_events:
            return

        for star in self.game.stars.filter(player__isnull=False, colonists__gt=0):
            if random.random() < RANDOM_EVENT_CHANCE:
                self._trigger_random_event(star)

    def _trigger_random_event(self, star):
        """Select and apply a random event to a star."""
        player = star.player
        luck = player.race_type.luck_multiplier

        # Event pool with base weights (positive weight, negative weight)
        # Luck multiplier increases positive weights, decreases negative
        events = [
            ('planetoid', 0.3, 0.3),  # Neutral - can go either way
            ('population_boom', 0.2 * luck, 0),
            ('mining_discovery', 0.2 * luck, 0),
            ('mining_accident_deaths', 0, 0.15 / luck),
            ('mining_accident_resources', 0, 0.1 / luck),
            ('colony_vanished', 0, 0.02 / luck),  # Rare extreme
        ]

        # Calculate total weights and select
        total = sum(e[1] + e[2] for e in events)
        roll = random.random() * total
        cumulative = 0
        selected = None
        for event_type, pos_weight, neg_weight in events:
            cumulative += pos_weight + neg_weight
            if roll < cumulative:
                selected = event_type
                break

        self._apply_random_event(star, selected)

    def _apply_random_event(self, star, event_type):
        """Apply a specific random event and create message."""
        if event_type == 'planetoid':
            self._apply_planetoid_event(star)
        elif event_type == 'population_boom':
            self._apply_population_boom(star)
        elif event_type == 'mining_discovery':
            self._apply_mining_discovery(star)
        elif event_type == 'mining_accident_deaths':
            self._apply_mining_accident_deaths(star)
        elif event_type == 'mining_accident_resources':
            self._apply_mining_accident_resources(star)
        elif event_type == 'colony_vanished':
            self._apply_colony_vanished(star)

    def _apply_planetoid_event(self, star):
        """Apply environmental nudge from passing planetoid."""
        player = star.player
        luck = player.race_type.luck_multiplier
        # Luck biases toward positive: range shifts from [-0.5, 0.5] toward positive
        intensity = random.uniform(-0.5, 0.5) + (luck - 1.0) * 0.3
        intensity = max(-1.0, min(1.0, intensity))

        # Pick 1-3 environmental factors to affect
        envs = random.sample(['gravity', 'temperature', 'radiation'],
                             k=random.randint(1, 3))
        for env in envs:
            current = getattr(star, env)
            ideal = getattr(player, f'{env}_center')
            # Positive intensity moves toward player's ideal, negative moves away
            direction = 1 if ideal > current else -1
            if intensity < 0:
                direction = -direction
            nudge = random.uniform(0.05, 0.15) * direction
            new_value = max(0.0, min(2.0, current + nudge))
            setattr(star, env, new_value)
        star.save()

        factory = PlanetoidEventMessageFactory(self.game, star.player, star, intensity=intensity)
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def _apply_population_boom(self, star):
        """Apply population boom - 5-15% increase."""
        increase_pct = random.uniform(0.05, 0.15)
        increase = max(1, int(star.colonists * increase_pct))
        star.colonists += increase
        star.save()

        factory = PopulationBoomMessageFactory(self.game, star.player, star, increase)
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def _apply_mining_discovery(self, star):
        """Apply resource discovery - add 10-30 kt to random surface resource."""
        resource = random.choice(['ironium', 'boranium', 'germanium'])
        qty = random.randint(10, 30)
        inventory_field = f'{resource}_inventory'
        current = getattr(star, inventory_field)
        setattr(star, inventory_field, current + qty)
        star.save()

        factory = MiningDiscoveryMessageFactory(self.game, star.player, star, qty, resource)
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def _apply_mining_accident_deaths(self, star):
        """Apply mining accident with colonist deaths - 2-10% loss."""
        loss_pct = random.uniform(0.02, 0.10)
        deaths = max(1, int(star.colonists * loss_pct))
        star.colonists = max(0, star.colonists - deaths)
        star.save()

        if star.colonists > 0:
            factory = MiningAccidentDeathsMessageFactory(self.game, star.player, star, deaths)
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()

    def _apply_mining_accident_resources(self, star):
        """Apply mining accident with surface resource loss - 5-10% of one resource."""
        resource = random.choice(['ironium', 'boranium', 'germanium'])
        inventory_field = f'{resource}_inventory'
        current = getattr(star, inventory_field)
        if current == 0:
            return  # Nothing to lose
        loss_pct = random.uniform(0.05, 0.10)
        loss = max(1, int(current * loss_pct))
        setattr(star, inventory_field, max(0, current - loss))
        star.save()

        factory = MiningAccidentResourcesMessageFactory(self.game, star.player, star, loss, resource)
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def _apply_colony_vanished(self, star):
        """Apply colony vanished - complete loss (extreme rare)."""
        factory = ColonyVanishedMessageFactory(self.game, star.player, star)
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

        # Clear the colony
        star.colonists = 0
        star.production_orders.all().delete()
        star.player = None
        star.save()


def apply_population_change(population, factor):
    """Apply population growth or decline based on factor.

    Positive factor: additive growth (pop += pop * factor)
    Negative factor: linear decline (pop *= survival_rate), min 1 loss to prevent infinite decay

    For declining populations under 1000, calculate decline based on 1000 colonists.
    This speeds up colony death for very small populations instead of lingering.
    """
    if factor >= 0:
        return population + int(population * factor)
    else:
        # Linear decline: survival_rate = 1 - |factor|, capped at 0% survival
        survival_rate = max(0, 1 - abs(factor))

        # For small declining colonies, calculate decline based on 1000 colonists minimum
        # This prevents drawn-out deaths where <10 colonists lose 1-2 per year
        base_pop = max(population, 1000)
        decline = int(base_pop * (1 - survival_rate))

        new_pop = population - decline
        # Ensure at least 1 colonist dies to prevent infinite decay
        new_pop = min(new_pop, population - 1)
        return max(0, new_pop)
