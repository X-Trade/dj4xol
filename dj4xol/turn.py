from datetime import timedelta
from math import atan2, atanh, ceil, cos, degrees, log2, pi, sin, sqrt, tanh
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
    FleetWormholeFuelFailureMessageFactory,
    FleetWormholeJumpSuccessMessageFactory,
    FleetWarpDestroyedMessageFactory,
    FleetWormholeDestroyedMessageFactory,
    FleetMergedMessageFactory,
    FleetTransferredMessageFactory,
    FleetReceivedMessageFactory,
    FleetOrdersCompletedMessageFactory,
    FleetBuildBlockedNoShipyardMessageFactory,
    FleetRepairedMessageFactory,
    OrbitalDefenseHitMessageFactory,
    TransferRaidThwartedMessageFactory,
    FleetBombardmentReportMessageFactory,
    BombardFailedNoStarMessageFactory,
    StarVanishedOminousMessageFactory,
    ResearchLevelUnlockedMessageFactory,
    ResearchBreakthroughMessageFactory,
    ScannerHabitableWorldRollupMessageFactory,
    SecretResourceDiscoveryMessageFactory,
    UnexplainedScanContactMessageFactory,
    AnomalyTargetLostMessageFactory,
    DiplomaticStanceChangedMessageFactory,
    format_map_object,
    format_location,
    map_coordinate_link,
)
import random
from .diplomacy import (
    PERMISSION_ALLOW_TRANSFER_RAID_DEFENSE,
    PERMISSION_ALLOW_TRANSFER_RAID_ROLL,
    PERMISSION_ORBITAL_DEFENSE_CHANCE_SCALE,
    PERMISSION_SHARE_INTEL,
    PERMISSION_SHIPYARD_REPAIR_RATE,
    build_stance_map,
    apply_pending_diplomacy_snapshot,
    combat_chance_percent,
    combat_chance_with_diplomacy_percent,
    combined_diplomacy_chance_scale,
    combat_readiness_multiplier,
    ensure_contact_stance_entry,
    player_grants_permission,
    player_permission_value,
    player_reveals_cloaked_fleets,
    shared_colony_report_policy,
    shared_fleet_report_policy,
    stance_label,
    stance_towards,
)
from .diplomatic_contracts import (
    apply_give_fleet_delivery,
    apply_world_resource_delivery,
    refresh_contract_integrity,
)
from .hazard_rules import (
    DANGER_NONE,
    DANGER_HIGH,
    DANGER_LOW,
    DANGER_MEDIUM,
    _pick_level,
    anomaly_danger_level,
    damage_intensity_multiplier,
    direct_destruction_allowed,
    hazard_trigger_chance,
    reward_intensity_multiplier,
    salvage_danger_level,
)

from .mineral_rules import ALL_RESOURCE_KEYS, random_asteroid_field_minerals, random_ancient_debris_minerals
from .secret_resources import SECRET_RESOURCE_KEYS, get_secret_resource_name, get_secret_resource_label
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
    calculate_available_buildpoints,
    calculate_available_construction_colonists,
    calculate_available_researchpoints,
    calculate_total_jobs,
    calculate_staffing_ratio,
    calculate_productivity_multiplier,
    calculate_consumed_buildpoints,
    calculate_productivity_percent,
    calculate_economy_percent,
    calculate_economy_factor,
    calculate_habitability_factor,
    calculate_growth_factor,
    calculate_effective_defenses,
    has_active_dyson_sphere,
    limit_population_growth_by_surface_resources,
    population_growth_uses_surface_resources,
    OVERMINING_DEPLETION_MULTIPLIER,
)
from .research import (
    process_player_research_for_year,
    get_player_administration_profile,
    get_player_colony_scanner_ranges,
    get_player_tech_effects,
    get_player_colony_defense_level,
    apply_research_bonus_rp,
    ensure_player_research_rows,
    get_global_research_max_level,
    get_player_dyson_sphere_profile,
    get_player_production_costs,
    get_player_terraforming_profile,
)
from .micromanager_rules import (
    ADMINISTRATION_ORDER_TYPE,
    DYSON_SPHERE_ORDER_TYPE,
    REMOVE_ADMINISTRATION_ORDER_TYPE,
    collapse_micromanager_order_totals,
    get_micromanager_managed_order_types,
    projected_mining_output,
    remaining_queue_requirements,
    plan_micromanager_orders,
)
from .ai_players import get_ai_check_in_turns, player_ai_administration_tier
from .fleet_thumbnails import choose_fleet_thumbnail
from .chance_rules import (
    apply_roll_bend,
    clamp_percent,
    roll_chance as chance_roll,
    scaled_luck_roll,
    luck_ratio_chance,
    transfer_raid_success_chance,
    anomaly_collapse_chance,
    anomaly_decay_chance,
    anomaly_spawn_chance,
)
from .bombardment_rules import (
    bombardment_damage_k,
    normalize_bomb_type,
    normalize_miner_type,
    smart_bombs_only_target_defenses_and_population,
)
from .scanners import (
    fleet_is_cloaked,
    fleet_targetable_by_patrol,
    fleet_visible_to_player,
    get_owned_scanner_sources_for_player,
    get_scanner_sources_for_player,
    position_in_scanner_range,
)

# Population carrying capacity constants now live in colony_rules.py

TURN_INTERVALS = {
    'HOURLY': timedelta(hours=1),
    'DAILY': timedelta(days=1),
    'WEEKLY': timedelta(weeks=1),
}


def format_basic_unknown_fleet_name(fleet):
    """Return the concealed label for basic fleet reports."""
    return 'Unknown Fleet'


def format_basic_hidden_salvage_name(salvage):
    """Return the concealed label for basic scanner salvage reports."""
    if getattr(salvage, 'salvage_type', None) == 'ANCIENT_DEBRIS':
        return '???'
    return getattr(salvage, 'name', '') or ''


# Random event probability per colonized star per turn
RANDOM_EVENT_CHANCE = 0.01  # 1%
RESEARCH_BREAKTHROUGH_CHANCE = 0.08  # 8% per player-year with active labs

# Mining constants
KT_PER_MINE = 10  # kt per mine per turn

# Warp damage constants
WARP_DESTRUCTION_THRESHOLD = 10  # Warp speed at which destruction becomes possible
WARP_DESTRUCTION_CHANCE = 0.30   # 30% chance of instant destruction at warp >= 10
WARP_DAMAGE_CHANCE_PER_EXCESS = 0.15  # 15% damage chance per excess warp factor
WORMHOLE_WARPFACTOR = 14
WORMHOLE_ARRIVAL_CHANCE = 0.60
WORMHOLE_DEVIATION_CHANCE = 0.75
WORMHOLE_DEVIATION_MIN_DISTANCE = 11.0
WORMHOLE_DEVIATION_LY_PER_50 = 5.0
WORMHOLE_INTEGRITY_DAMAGE_CHANCE = 0.20
WORMHOLE_MAX_INTEGRITY_DAMAGE_PER_100_LY = 1
WORMHOLE_DESTRUCTION_CHANCE = 0.10
WORMHOLE_RIFT_MIN_DISTANCE = 4.0
WORMHOLE_RIFT_MAX_DISTANCE = 9.0
WORMHOLE_DRIVE_RIFT_CHANCE = 0.01
WORMHOLE_DRIVE_BLACK_HOLE_CHANCE = 0.02
WORMHOLE_DRIVE_WORMHOLE_CHANCE = 0.03
WORMHOLE_DRIVE_WORMHOLE_STABILITY_MIN = 20
WORMHOLE_DRIVE_WORMHOLE_STABILITY_MAX = 60

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
COMBAT_AMBUSH_ATTACK_MIN = 1.05
COMBAT_AMBUSH_ATTACK_MAX = 1.30
ORBITAL_DEFENSE_HAZARD_BASE_CHANCE = 0.15
ORBITAL_DEFENSE_HAZARD_MIN_CHANCE = 0.10
ORBITAL_DEFENSE_HAZARD_MAX_CHANCE = 0.20
ORBITAL_DEFENSE_HAZARD_DAMAGE_FACTOR = 0.25
MERGE_COMBAT_RETENTION = 0.95
BUSSARD_RECOVERY_CHANCE = 0.5
BUSSARD_RECOVERY_MIN_MG = 1
BUSSARD_RECOVERY_MAX_MG = 5
FUEL_CONSUMPTION_MULTIPLIER = 2.0
NOVA_STAR_DESTRUCTION_CHANCE = 0.40
NOVA_BLACK_HOLE_SPAWN_CHANCE = 0.10
NOVA_ASTEROID_FIELD_SPAWN_CHANCE = 0.40
NOVA_ASTEROID_FIELD_EXPOSED_POTENTIAL_FRACTION = 0.05
STAR_VANISH_FLEET_MENTION_CHANCE = 0.35
REMOTE_MINER_UNITS_BY_TYPE = {
    'SMALL': 1,
    'MEDIUM': 2,
    'LARGE': 4,
}
REMOTE_MINE_HARASS_CHANCE = 0.35
REMOTE_MINE_HARASS_DAMAGE_FACTOR = 0.25
REMOTE_MINE_DEFENSE_DAMAGE_MULTIPLIER = 1.25
THEFT_DEFENSE_DAMAGE_MIN_MULTIPLIER = 1.0
THEFT_DEFENSE_DAMAGE_MAX_MULTIPLIER = 1.5
THEFT_LUCK_JITTER = 0.25
THEFT_SUCCESS_DAMAGE_WEIGHT = 0.5
THEFT_SUCCESS_SHIP_WEIGHT = 0.4
THEFT_SUCCESS_MIN_CHANCE = 0.0
THEFT_SUCCESS_MAX_CHANCE = 1.0
DERELICT_CLAIM_CHANCE = 0.55
DEFEATED_FLEET_CAPTURE_CHANCE = 0.45
DEFEATED_FLEET_SCUTTLE_CHANCE = 0.25
DEFEATED_FLEET_ABANDON_CHANCE = 0.30
ANOMALY_DAMAGE_MIN = 8
ANOMALY_DAMAGE_MAX = 30
ANOMALY_CARGO_LOSS_MIN = 0.10
ANOMALY_CARGO_LOSS_MAX = 0.45
ANOMALY_BONUS_RP_MIN = 150
ANOMALY_BONUS_RP_MAX = 1500
ANOMALY_MAJOR_PROGRESS_RP_MIN = 500
ANOMALY_MAJOR_PROGRESS_RP_MAX = 900
ANOMALY_SPAWN_CHANCE_PER_YEAR = 0.02
ANOMALY_EMPTY_MAP_SPAWN_CHANCE = 0.45
ASTEROID_FIELD_SPAWN_SHARE = 0.25
ANCIENT_DEBRIS_SPAWN_SHARE = 0.02

ASTEROID_FIELD_DAMAGE_MIN = 1
ASTEROID_FIELD_DAMAGE_MAX = 4
ANCIENT_DEBRIS_DAMAGE_MIN = 40
ANCIENT_DEBRIS_DAMAGE_MAX = 90
ANOMALY_MAX_STAR_RATIO = 0.15
ANOMALY_COMET_DRIFT_WARP = 1.0
ANOMALY_MAX_RISK_REWARD_BONUS = 0.50
WORMHOLE_DAMAGE_MAX = 85
WORMHOLE_EXIT_MIN_DISTANCE = 4.0
WORMHOLE_EXIT_MAX_DISTANCE = 8.0
WORMHOLE_WANDER_MAX_LY_PER_YEAR = 12.0
WORMHOLE_INSTANT_DESTRUCTION_MAX_CHANCE = 0.35
MICROMANAGER_FLEET_TIER = 4
MICROMANAGER_ADVANCED_FLEET_TIER = 5
MICROMANAGER_FLEET_DISPATCHES_PER_COLONY = 1
MICROMANAGER_DEFENSE_FLEET_RATIO = 0.50
MICROMANAGER_DEFENSE_SHIP_RATIO = 0.50
MICROMANAGER_ASTEROID_SEARCH_RADIUS = 18.0
MICROMANAGER_MAX_ORBIT_FLEETS = 5
MICROMANAGER_FLEET_BUILD_MAX_YEARS = 3
MICROMANAGER_COLONISE_DISPATCHES_PER_COLONY = 1
MICROMANAGER_COLONISE_SEARCH_RADIUS = 20.0
MICROMANAGER_COLONISE_MIN_PAYLOAD = 5
MICROMANAGER_COLONISE_RESERVE_COLONISTS = 50
MICROMANAGER_PATROL_IDLE_RATIO = 0.25
MICROMANAGER_PATROL_RADIUS = 15


# Chance calculation functions (separated for testability)
def roll_chance(threshold):
    """Return True if random roll is below threshold."""
    return chance_roll(threshold)


def format_readable_list(items):
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


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


def roll_ambush_attack_multiplier(luck_multiplier):
    """Roll a modest offense boost for a fresh cloaked intercept ambush."""
    return scaled_luck_roll(
        luck_multiplier,
        min_scale=COMBAT_AMBUSH_ATTACK_MIN,
        max_scale=COMBAT_AMBUSH_ATTACK_MAX,
        bend=COMBAT_ATTACK_ROLL_BEND,
    )


def calculate_integrity_loss(excess_warp):
    """Calculate integrity loss from warp damage (5-15% per excess warp)."""
    return sum(random.randint(5, 15) for _ in range(excess_warp))


def calculate_cargo_loss_percent(excess_warp):
    """Calculate cargo loss percentage from warp damage (2-10% per excess warp)."""
    return sum(random.randint(2, 10) for _ in range(excess_warp)) / 100.0


def calculate_salvage_minerals(
    dry_mass,
    cargo_iron,
    cargo_bor,
    cargo_germ,
    cargo_resource_x=0,
    cargo_resource_y=0,
    cargo_resource_z=0,
):
    """Calculate salvage minerals from a destroyed/scuttled fleet.

    Uses the same dry_mass split formula as colonise (random distribution).
    Applies random degradation (30-70% loss) to simulate battle damage.
    Returns (ironium, boranium, germanium, resource_x, resource_y, resource_z) tuple.
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
    total_resource_x = int(cargo_resource_x or 0)
    total_resource_y = int(cargo_resource_y or 0)
    total_resource_z = int(cargo_resource_z or 0)

    # Apply random degradation (30-70% survives)
    survival_rate = random.uniform(
        1.0 - SALVAGE_DEGRADATION_MAX,
        1.0 - SALVAGE_DEGRADATION_MIN
    )
    return (
        int(total_iron * survival_rate),
        int(total_bor * survival_rate),
        int(total_germ * survival_rate),
        int(total_resource_x * survival_rate),
        int(total_resource_y * survival_rate),
        int(total_resource_z * survival_rate),
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
    race_mult = fleet.player.race_type.combat_multiplier
    return race_mult * tech_level_to_multiplier(fleet.defense_level)


def calculate_fleet_strength(
    fleet,
    opponent_defence_multiplier,
    attack_roll_scale=1.0,
    offense_bonus_multiplier=1.0,
):
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
    try:
        offense_bonus = float(offense_bonus_multiplier)
    except (TypeError, ValueError):
        offense_bonus = 1.0
    attack_mult *= max(0.0, offense_bonus)
    defence_factor = 1.0 / opponent_defence_multiplier if opponent_defence_multiplier else 1.0
    base = count_norm * attack_mult * defence_factor
    integrity_factor = (2.0 * integrity_norm) - (integrity_norm ** 2)
    strength = base * integrity_factor
    return max(0.0, strength)


class GameTurn():
    """Generate a turn for a game."""
    def __init__(self, game):
        self.game = game
        self._scanner_sources_by_player_id = {}
        self._first_contact_sent = set()
        self._first_contact_any_sent = set()
        self._stance_map_by_player_id = {}
        self._ambush_fleet_ids_for_year = set()

    def generate_turn(self):
        """Generate a turn for the game. Requires at least one player."""
        if self.game.is_generating:
            raise Exception("Turn generation already in progress")
        if not self.game.players.exists():
            raise Exception("cannot generate turn for game with no players")
        self._update_ai_checkin_state(auto_turn_in=False)

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
        self._scanner_sources_by_player_id = {}
        self._stance_map_by_player_id = {}
        refresh_contract_integrity(self.game)
        self._apply_pending_diplomacy_snapshot()
        self.move_comets()
        self.move_wormholes()
        self.decay_anomalies()
        self.fleet_movements()
        self.anomaly_interactions()
        self.salvage_interactions()
        self.check_lost_fleets()
        self.check_damaged_fleets()
        self.first_contact_checks()
        self.resolve_combat()
        self.resolve_derelict_encounters()
        self.resolve_orbital_defense_hazards()
        self.apply_fuel_factories()
        self.mining()
        self.production()
        self.research()
        self.population_growth()
        self.random_events()
        self.spawn_anomalies()
        self.clear_empty_planets()
        self.check_join_deadline()
        self.generate_scanner_reports()
        self.generate_reports()
        self.generate_shared_intel_reports()
        self.game.year += 1

    def _apply_pending_diplomacy_snapshot(self):
        """Apply staged diplomacy updates and notify affected players."""
        changes = apply_pending_diplomacy_snapshot(self.game)
        for change in changes:
            target_player = change.get('target_player')
            source_player = change.get('source_player')
            new_stance = change.get('new_stance')
            if not target_player or not source_player:
                continue
            factory = DiplomaticStanceChangedMessageFactory(
                self.game,
                target_player,
                source_player,
                stance_label(new_stance),
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()

    @staticmethod
    def _anomaly_stability(anomaly):
        return int(clamp_percent(getattr(anomaly, 'stability', 100), default=100.0))

    @classmethod
    def _anomaly_instability_ratio(cls, anomaly):
        """Return 0.0 at stability=100, 1.0 at stability=0."""
        stability = cls._anomaly_stability(anomaly)
        return (100.0 - float(stability)) / 100.0

    @classmethod
    def _anomaly_risk_reward_multiplier(cls, anomaly):
        """Return 1.0..1.5 multiplier based on instability."""
        return 1.0 + (cls._anomaly_instability_ratio(anomaly) * ANOMALY_MAX_RISK_REWARD_BONUS)

    def _apply_anomaly_breakthrough(self, player, anomaly):
        rows = ensure_player_research_rows(player)
        if not rows:
            return False
        max_level = int(get_global_research_max_level() or 0)
        eligible = [
            row for row in rows
            if int(getattr(row, 'current_level', 0) or 0) < max_level
        ]
        if not eligible:
            return False
        row = random.choice(eligible)
        old_level = int(row.current_level or 0)
        row.current_level = max_level
        row.save(update_fields=['current_level'])
        self._create_research_unlock_messages(player, [{
            'category': row.category,
            'old_level': old_level,
            'new_level': int(row.current_level or 0),
        }])
        self._create_anomaly_message(
            player,
            "Anomaly breakthrough at %s completed %s research, advancing it to level %s." % (
                format_map_object(anomaly), row.category.name, int(row.current_level or 0)
            ),
            priority=False,
        )
        return True

    def decay_anomalies(self):
        """Decay unstable anomalies and collapse very unstable anomalies over time."""
        if not bool(getattr(self.game, 'anomalies_enabled', False)):
            return
        from .models import Anomaly

        for anomaly in list(Anomaly.objects.filter(game=self.game)):
            anomaly = Anomaly.objects.filter(id=anomaly.id).first()
            if anomaly is None:
                continue
            stability = self._anomaly_stability(anomaly)
            changed = False
            decay_chance = anomaly_decay_chance(stability)
            if decay_chance > 0.0 and random.random() < decay_chance:
                stability = max(0, stability - 1)
                anomaly.stability = stability
                changed = True
            collapse_chance = anomaly_collapse_chance(stability)
            if collapse_chance > 0.0 and random.random() < collapse_chance:
                self._retarget_or_remove_orders_for_destroyed_anomaly(
                    anomaly.name, anomaly.short_id, anomaly.x, anomaly.y, anomaly.anomaly_type
                )
                if getattr(anomaly, 'anomaly_type', None) == Anomaly.TYPE_WORMHOLE:
                    self._resolve_wormhole_extinction(anomaly)
                anomaly.delete()
                continue
            if changed:
                anomaly.save(update_fields=['stability'])

    def _resolve_wormhole_extinction(self, anomaly):
        """When one wormhole endpoint dies, the pair collapses or becomes an unstable black hole."""
        from .models import Anomaly

        pair = getattr(anomaly, 'wormhole_pair', None)
        if not pair:
            return
        if not Anomaly.objects.filter(id=pair.id).exists():
            return
        pair = Anomaly.objects.get(id=pair.id)
        pair.wormhole_pair = None
        if random.random() < 0.5:
            self._retarget_or_remove_orders_for_destroyed_anomaly(
                pair.name, pair.short_id, pair.x, pair.y, pair.anomaly_type
            )
            pair.delete()
            return
        pair.anomaly_type = Anomaly.TYPE_BLACK_HOLE
        pair.stability = random.randint(1, 49)
        pair.heading = random.random() * 360.0
        pair.name = 'Black Hole %s' % (Anomaly.objects.filter(game=self.game).count() + 1)
        pair.save(update_fields=['wormhole_pair', 'anomaly_type', 'stability', 'heading', 'name'])

    def _retarget_or_remove_orders_for_destroyed_anomaly(
        self, anomaly_name, anomaly_short_id, x, y, anomaly_type
    ):
        """Convert anomaly-bound movement targets to space and warn affected players once."""
        from .models import FleetOrders

        orders = FleetOrders.objects.filter(
            game=self.game,
            target_kind='OBJECT',
            target_short_id=anomaly_short_id,
        ).select_related('fleet__player').order_by('fleet__player_id', 'position', 'id')
        if not orders.exists():
            return

        warned_players = set()
        for order in orders:
            fleet = getattr(order, 'fleet', None)
            player = getattr(fleet, 'player', None) if fleet is not None else None
            if player is None or player.id in warned_players:
                continue
            factory = AnomalyTargetLostMessageFactory(
                self.game, player, fleet, anomaly_name, anomaly_type, x, y
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()
            warned_players.add(player.id)

        movement_types = ['MOVE', 'INTERCEPT', 'PATROL']
        orders.filter(order_type__in=movement_types).update(
            target_kind='SPACE',
            target_short_id=None,
            x=int(x),
            y=int(y),
        )
        orders.exclude(order_type__in=movement_types).delete()

    def _quantized_axis_step(self, component, comet_short_id, axis_key, year=None):
        """Convert a sub-integer movement component into deterministic yearly tile steps."""
        try:
            value = float(component)
        except (TypeError, ValueError):
            return 0
        magnitude = abs(value)
        if magnitude < 1e-9:
            return 0
        sid = str(comet_short_id or '')
        seed = sum((idx + 1) * ord(ch) for idx, ch in enumerate('%s:%s' % (sid, axis_key)))
        phase = (seed % 997) / 997.0
        if year is None:
            year = self.game.year
        year = float(year or 0)
        before = int((year + phase) * magnitude)
        after = int((year + 1.0 + phase) * magnitude)
        step = max(0, after - before)
        if step <= 0:
            return 0
        return step if value > 0 else -step

    @staticmethod
    def _normalize_heading(heading):
        """Normalize a heading to [0, 360)."""
        try:
            return float(heading) % 360.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _signed_heading_delta(target_heading, current_heading):
        """Shortest signed heading delta in degrees (-180, 180]."""
        return ((target_heading - current_heading + 540.0) % 360.0) - 180.0

    @staticmethod
    def _closest_distance_to_step_segment(start_x, start_y, dx, dy, star_x, star_y):
        """Return minimum distance from a star to the comet's one-turn movement segment."""
        end_x = float(start_x) + float(dx)
        end_y = float(start_y) + float(dy)
        seg_x = end_x - float(start_x)
        seg_y = end_y - float(start_y)
        seg_len_sq = (seg_x * seg_x) + (seg_y * seg_y)
        if seg_len_sq <= 0.0:
            proj_x = float(start_x)
            proj_y = float(start_y)
        else:
            rel_x = float(star_x) - float(start_x)
            rel_y = float(star_y) - float(start_y)
            t = ((rel_x * seg_x) + (rel_y * seg_y)) / seg_len_sq
            t = max(0.0, min(1.0, t))
            proj_x = float(start_x) + (seg_x * t)
            proj_y = float(start_y) + (seg_y * t)
        diff_x = float(star_x) - proj_x
        diff_y = float(star_y) - proj_y
        return ((diff_x * diff_x) + (diff_y * diff_y)) ** 0.5

    def move_comets(self):
        """Drift comet anomalies according to heading at a low fixed warp."""
        if not bool(getattr(self.game, 'anomalies_enabled', False)):
            return
        from .models import Anomaly, Star

        max_x = max(1, int(self.game.map_size_x) - 1)
        max_y = max(1, int(self.game.map_size_y) - 1)
        stars = list(Star.objects.filter(game=self.game).only('x', 'y'))
        comets = list(Anomaly.objects.filter(
            game=self.game,
            anomaly_type=Anomaly.TYPE_COMET,
        ))
        if not comets:
            return

        for comet in comets:
            heading = self._normalize_heading(comet.heading)
            angle = heading * pi / 180.0
            dx = sin(angle) * ANOMALY_COMET_DRIFT_WARP
            dy = -cos(angle) * ANOMALY_COMET_DRIFT_WARP
            nearest_star = None
            nearest_distance = None
            for star in stars:
                distance = self._closest_distance_to_step_segment(
                    comet.x, comet.y, dx, dy, star.x, star.y
                )
                if distance > 1.0:
                    continue
                to_star_x = float(star.x) - float(comet.x)
                to_star_y = float(star.y) - float(comet.y)
                forward_dot = (to_star_x * dx) + (to_star_y * dy)
                # Ignore stars that are behind current motion direction.
                if distance >= 1e-9 and forward_dot < 0.0:
                    continue
                if nearest_distance is None or distance < nearest_distance:
                    nearest_distance = distance
                    nearest_star = star
            if nearest_star is not None and nearest_distance is not None:
                if nearest_distance < 1e-9:
                    heading = (heading + random.uniform(-179.0, 179.0)) % 360.0
                else:
                    star_dx = float(nearest_star.x) - float(comet.x)
                    star_dy = float(nearest_star.y) - float(comet.y)
                    star_heading = (degrees(atan2(star_dx, -star_dy)) + 360.0) % 360.0
                    max_turn = 60.0 + ((1.0 - nearest_distance) * 119.0)
                    delta = self._signed_heading_delta(star_heading, heading)
                    delta = max(-max_turn, min(max_turn, delta))
                    heading = (heading + delta) % 360.0
                angle = heading * pi / 180.0
                dx = sin(angle) * ANOMALY_COMET_DRIFT_WARP
                dy = -cos(angle) * ANOMALY_COMET_DRIFT_WARP

            step_x = self._quantized_axis_step(dx, comet.short_id, 'x')
            step_y = self._quantized_axis_step(dy, comet.short_id, 'y')
            new_x = int(comet.x) + step_x
            new_y = int(comet.y) + step_y

            if new_x < 1 or new_x > max_x or new_y < 1 or new_y > max_y:
                comet.delete()
                continue

            comet.x = int(new_x)
            comet.y = int(new_y)
            comet.heading = float(heading)
            comet.save(update_fields=['x', 'y', 'heading'])

    def _find_wormhole_exit(self, endpoint, origin):
        """Return a valid exit coordinate near endpoint, avoiding stars/anomalies and the endpoint tile."""
        from .models import Star, Anomaly

        max_x = max(1, int(self.game.map_size_x) - 1)
        max_y = max(1, int(self.game.map_size_y) - 1)
        occupied = set(Star.objects.filter(game=self.game).values_list('x', 'y'))
        occupied.update(
            Anomaly.objects.filter(game=self.game).exclude(id=origin.id).values_list('x', 'y')
        )
        candidates = []
        max_d = int(ceil(WORMHOLE_EXIT_MAX_DISTANCE))
        for ox in range(-max_d, max_d + 1):
            for oy in range(-max_d, max_d + 1):
                dist = ((ox * ox) + (oy * oy)) ** 0.5
                if WORMHOLE_EXIT_MIN_DISTANCE <= dist <= WORMHOLE_EXIT_MAX_DISTANCE:
                    x = int(endpoint.x + ox)
                    y = int(endpoint.y + oy)
                    if x < 1 or x > max_x or y < 1 or y > max_y:
                        continue
                    if (x, y) in occupied:
                        continue
                    candidates.append((x, y))
        random.shuffle(candidates)
        if candidates:
            return candidates[0]
        fallback_x = int(endpoint.x + int(WORMHOLE_EXIT_MIN_DISTANCE))
        fallback_y = int(endpoint.y)
        fallback_x = max(1, min(max_x, fallback_x))
        fallback_y = max(1, min(max_y, fallback_y))
        if (fallback_x, fallback_y) == (int(endpoint.x), int(endpoint.y)):
            fallback_x = max(1, min(max_x, int(endpoint.x - int(WORMHOLE_EXIT_MIN_DISTANCE))))
        return fallback_x, fallback_y

    def _move_anomaly_within_map(self, anomaly, max_step, star_positions, occupied_positions):
        """Move anomaly by up to max_step LY, avoiding stars and occupied anomaly tiles."""
        max_step = max(0, int(max_step or 0))
        if max_step <= 0:
            return
        max_x = max(1, int(self.game.map_size_x) - 1)
        max_y = max(1, int(self.game.map_size_y) - 1)
        base_x = int(anomaly.x)
        base_y = int(anomaly.y)
        offsets = [(0, 0)]
        for ox in range(-max_step, max_step + 1):
            for oy in range(-max_step, max_step + 1):
                if ox == 0 and oy == 0:
                    continue
                dist = ((ox * ox) + (oy * oy)) ** 0.5
                if dist <= float(max_step):
                    offsets.append((ox, oy))
        random.shuffle(offsets)
        for ox, oy in offsets:
            nx = base_x + ox
            ny = base_y + oy
            if nx < 1 or nx > max_x or ny < 1 or ny > max_y:
                continue
            if (nx, ny) in star_positions:
                continue
            if (nx, ny) in occupied_positions and (nx, ny) != (base_x, base_y):
                continue
            occupied_positions.discard((base_x, base_y))
            anomaly.x = int(nx)
            anomaly.y = int(ny)
            occupied_positions.add((int(nx), int(ny)))
            anomaly.save(update_fields=['x', 'y'])
            return

    def move_wormholes(self):
        """Wormhole endpoints wander based on instability, up to 12LY/year at low stability."""
        if not bool(getattr(self.game, 'anomalies_enabled', False)):
            return
        from .models import Anomaly, Star

        wormholes = list(Anomaly.objects.filter(
            game=self.game,
            anomaly_type=Anomaly.TYPE_WORMHOLE,
        ))
        if not wormholes:
            return
        star_positions = set(Star.objects.filter(game=self.game).values_list('x', 'y'))
        occupied_positions = set(
            Anomaly.objects.filter(game=self.game).values_list('x', 'y')
        )
        for wormhole in wormholes:
            instability = self._anomaly_instability_ratio(wormhole)
            max_step = int(round(float(WORMHOLE_WANDER_MAX_LY_PER_YEAR) * instability))
            self._move_anomaly_within_map(
                wormhole, max_step, star_positions, occupied_positions
            )

    def anomaly_interactions(self):
        """Apply anomaly outcomes to fleets co-located with anomalies."""
        if not bool(getattr(self.game, 'anomalies_enabled', False)):
            return
        from .models import Fleet, Anomaly
        anomalies = list(Anomaly.objects.filter(game=self.game))
        if not anomalies:
            return
        anomaly_positions = {(a.x, a.y): a for a in anomalies}
        fleets = list(Fleet.objects.filter(game=self.game))
        for fleet in fleets:
            if fleet.player is None or bool(getattr(fleet.player, 'defeated', False)):
                continue
            anomaly = anomaly_positions.get((fleet.x, fleet.y))
            if anomaly is None:
                continue
            if getattr(anomaly, 'anomaly_type', None) == Anomaly.TYPE_WORMHOLE:
                self._apply_wormhole_interaction(fleet, anomaly)
                continue
            roll = random.randint(1, 6)
            danger_level = anomaly_danger_level(anomaly)
            if danger_level == DANGER_LOW:
                if roll == 1:
                    continue
                if roll == 2:
                    continue
                if roll == 3:
                    continue
                if roll == 4:
                    self._apply_anomaly_damage(fleet, anomaly)
                    continue
                if roll == 5:
                    self._apply_anomaly_cargo_loss(fleet, anomaly)
                    continue
                self._apply_anomaly_research_boon(
                    fleet, anomaly, allow_breakthrough=False, reward_tier='low'
                )
                continue
            if danger_level == DANGER_MEDIUM:
                if roll == 1:
                    continue
                if roll == 2:
                    continue
                if roll == 3:
                    self._apply_anomaly_damage(fleet, anomaly)
                    continue
                if roll == 4:
                    self._apply_anomaly_cargo_loss(fleet, anomaly)
                    continue
                if roll == 5:
                    self._apply_anomaly_research_boon(
                        fleet, anomaly, allow_breakthrough=False, reward_tier='low'
                    )
                    continue
                self._apply_anomaly_research_boon(
                    fleet, anomaly, allow_breakthrough=False, reward_tier='medium'
                )
                continue
            if danger_level == DANGER_HIGH:
                if roll == 1:
                    continue
                if roll == 2:
                    self._apply_anomaly_damage(fleet, anomaly)
                    continue
                if roll == 3:
                    self._apply_anomaly_cargo_loss(fleet, anomaly)
                    continue
                if roll == 4:
                    self._apply_anomaly_destruction(fleet, anomaly)
                    continue
                if roll == 5:
                    self._apply_anomaly_research_boon(
                        fleet, anomaly, allow_breakthrough=False, reward_tier='medium'
                    )
                    continue
                self._apply_anomaly_breakthrough(fleet.player, anomaly)
                continue
            if roll == 1:
                continue
            if roll == 2:
                self._apply_anomaly_damage(fleet, anomaly)
                continue
            if roll == 3:
                self._apply_anomaly_cargo_loss(fleet, anomaly)
                continue
            if roll == 4:
                self._apply_anomaly_research_boon(
                    fleet, anomaly, allow_breakthrough=False, reward_tier='low'
                )
                continue
            if roll == 5:
                self._apply_anomaly_research_boon(
                    fleet, anomaly, allow_breakthrough=False, reward_tier='medium'
                )
                continue
            self._apply_anomaly_breakthrough(fleet.player, anomaly)

    def salvage_interactions(self):
        """Apply salvage hazard damage to fleets co-located with special salvage."""
        from .models import Fleet, Salvage

        salvages = list(Salvage.objects.filter(game=self.game))
        if not salvages:
            return
        salvage_positions = {(s.x, s.y): s for s in salvages}
        fleets = list(Fleet.objects.filter(game=self.game))
        for fleet in fleets:
            if fleet.player is None or bool(getattr(fleet.player, 'defeated', False)):
                continue
            salvage = salvage_positions.get((fleet.x, fleet.y))
            if salvage is None:
                continue
            salvage_type = getattr(salvage, 'salvage_type', None)
            danger_level = salvage_danger_level(salvage)
            if not roll_chance(hazard_trigger_chance(danger_level)):
                continue
            if salvage_type in (Salvage.TYPE_SALVAGE, Salvage.TYPE_ASTEROID_FIELD):
                if salvage_type == Salvage.TYPE_ASTEROID_FIELD:
                    templates = [
                        "{fleet} took {damage}% integrity damage from rock strikes in {salvage}.",
                        "{fleet} took {damage}% integrity damage while sheltering in {salvage}.",
                        "{fleet} took {damage}% integrity damage from shifting debris in {salvage}.",
                    ]
                else:
                    templates = [
                        "{fleet} took {damage}% integrity damage while skimming unstable wreckage in {salvage}.",
                        "{fleet} took {damage}% integrity damage from drifting debris in {salvage}.",
                        "{fleet} took {damage}% integrity damage from a salvage collision in {salvage}.",
                    ]
                self._apply_salvage_damage(
                    fleet,
                    salvage,
                    ASTEROID_FIELD_DAMAGE_MIN,
                    ASTEROID_FIELD_DAMAGE_MAX,
                    danger_level=danger_level,
                    message_templates=templates,
                    message_priority=False,
                )
            elif salvage_type == Salvage.TYPE_ANCIENT_DEBRIS:
                templates = [
                    "Unknown forces within {salvage} inflicted {damage}% integrity damage on {fleet}.",
                    "Automated defences in {salvage} struck {fleet}, causing {damage}% integrity damage.",
                    "An unstable energy field in {salvage} reduced {fleet} integrity by {damage}%.",
                ]
                destruction_templates = [
                    "{fleet} was destroyed by the automated defences at {salvage}.",
                    "{fleet} was torn apart by unknown forces within {salvage}.",
                    "{fleet} was lost to an energy surge in {salvage}.",
                ]
                self._apply_salvage_damage(
                    fleet, salvage, ANCIENT_DEBRIS_DAMAGE_MIN, ANCIENT_DEBRIS_DAMAGE_MAX,
                    danger_level=danger_level,
                    message_templates=templates,
                    destruction_templates=destruction_templates,
                    allow_destroy=True,
                    min_defense_for_survival=10,
                    message_priority=True,
                    destruction_priority=True,
                )

    def _apply_salvage_damage(
        self,
        fleet,
        salvage,
        min_damage,
        max_damage,
        danger_level=None,
        message_templates=None,
        destruction_templates=None,
        allow_destroy=False,
        min_defense_for_survival=None,
        message_priority=True,
        destruction_priority=True,
    ):
        """Apply minor hazard damage when entering salvage fields."""
        try:
            base_damage = random.randint(int(min_damage), int(max_damage))
        except (TypeError, ValueError):
            base_damage = 0
        if base_damage <= 0:
            return
        try:
            defense_level = int(getattr(fleet, 'defense_level', 0) or 0)
        except (TypeError, ValueError):
            defense_level = 0
        defense_factor = 1.0 + (max(0, defense_level) / 2.0)
        scaled = int(round(
            (float(base_damage) * damage_intensity_multiplier(danger_level))
            / float(defense_factor)
        ))
        damage = max(0, scaled)
        if damage <= 0:
            return
        if not direct_destruction_allowed(danger_level):
            allow_destroy = False
        if allow_destroy and min_defense_for_survival is not None:
            if defense_level < int(min_defense_for_survival):
                deficit = int(min_defense_for_survival) - defense_level
                destruction_chance = min(1.0, max(0.0, deficit / float(min_defense_for_survival)))
                if roll_chance(destruction_chance):
                    player = fleet.player
                    fleet.delete()
                    if destruction_templates:
                        template = random.choice(destruction_templates)
                        text = template.format(
                            salvage=format_map_object(salvage),
                            fleet=fleet.name,
                        )
                    else:
                        text = "%s was destroyed while exploring %s." % (
                            fleet.name, format_map_object(salvage)
                        )
                    self._create_salvage_hazard_message(
                        player, text, priority=destruction_priority
                    )
                    return

        if int(fleet.integrity or 0) <= damage:
            if allow_destroy:
                player = fleet.player
                fleet.delete()
                if destruction_templates:
                    template = random.choice(destruction_templates)
                    text = template.format(
                        salvage=format_map_object(salvage),
                        fleet=fleet.name,
                    )
                else:
                    text = "%s was destroyed while exploring %s." % (
                        fleet.name, format_map_object(salvage)
                    )
                self._create_salvage_hazard_message(
                    player, text, priority=destruction_priority
                )
                return
            damage = max(0, int(fleet.integrity or 0) - 1)
        if damage <= 0:
            return
        fleet.integrity = max(0, int(fleet.integrity or 0) - damage)
        fleet.save(update_fields=['integrity'])
        if message_templates:
            template = random.choice(message_templates)
            text = template.format(
                salvage=format_map_object(salvage),
                damage=damage,
                fleet=format_map_object(fleet),
            )
            self._create_salvage_hazard_message(
                fleet.player, text, priority=message_priority
            )

    def _create_salvage_hazard_message(self, player, text, priority=False):
        from .models import GameMessage
        GameMessage.objects.create(
            game=self.game,
            player=player,
            message=text,
            year=self.game.year,
            category='RANDOM',
            priority=bool(priority),
        )

    def _random_empty_spawn_point(self, occupied, min_x, min_y, max_x, max_y, attempts=120):
        """Find an unoccupied coordinate for anomaly or salvage spawning."""
        for _ in range(attempts):
            x = random.randint(min_x, max_x)
            y = random.randint(min_y, max_y)
            if (x, y) in occupied:
                continue
            return x, y
        return None

    def _spawn_special_salvage(self, salvage_type, occupied, min_x, min_y, max_x, max_y):
        """Spawn special salvage fields that do not count toward the anomaly cap."""
        from .models import Salvage

        point = self._random_empty_spawn_point(occupied, min_x, min_y, max_x, max_y)
        if point is None:
            return False
        x, y = point
        if salvage_type == Salvage.TYPE_ANCIENT_DEBRIS:
            iron, bor, germ, res_x, res_y, res_z = random_ancient_debris_minerals()
            Salvage.objects.create(
                game=self.game,
                x=x,
                y=y,
                salvage_type=salvage_type,
                ironium_inventory=iron,
                boranium_inventory=bor,
                germanium_inventory=germ,
                resource_x_inventory=res_x,
                resource_y_inventory=res_y,
                resource_z_inventory=res_z,
            )
            return True
        if salvage_type == Salvage.TYPE_ASTEROID_FIELD:
            iron, bor, germ = random_asteroid_field_minerals()
            Salvage.objects.create(
                game=self.game,
                x=x,
                y=y,
                salvage_type=salvage_type,
                ironium_inventory=iron,
                boranium_inventory=bor,
                germanium_inventory=germ,
            )
            return True
        return False

    @staticmethod
    def _anomaly_spawn_rate_multiplier(rate):
        multiplier = 1.0
        if rate == 'HIGH':
            multiplier = 2.0
        elif rate == 'LOW':
            multiplier = 0.5
        return multiplier

    def spawn_anomalies(self):
        """Spawn rare special salvage and cap-aware anomalies."""
        if not bool(getattr(self.game, 'anomalies_enabled', False)):
            return
        rate = str(getattr(self.game, 'anomaly_spawn_rate', 'NORMAL') or 'NORMAL').upper()
        multiplier = self._anomaly_spawn_rate_multiplier(rate)
        from .models import (
            Anomaly, Star, Fleet, Salvage, random_anomaly_stability_init,
            random_wormhole_stability_init,
        )
        star_count = int(Star.objects.filter(game=self.game).count())
        if star_count <= 0:
            return

        occupied = set(Star.objects.filter(game=self.game).values_list('x', 'y'))
        occupied.update(Fleet.objects.filter(game=self.game).values_list('x', 'y'))
        occupied.update(Salvage.objects.filter(game=self.game).values_list('x', 'y'))
        occupied.update(Anomaly.objects.filter(game=self.game).values_list('x', 'y'))
        min_x = 1
        min_y = 1
        max_x = max(1, int(self.game.map_size_x) - 1)
        max_y = max(1, int(self.game.map_size_y) - 1)

        ancient_debris_chance = min(
            1.0,
            float(ANOMALY_SPAWN_CHANCE_PER_YEAR) * multiplier * float(ANCIENT_DEBRIS_SPAWN_SHARE),
        )
        if random.random() < ancient_debris_chance:
            self._spawn_special_salvage(
                Salvage.TYPE_ANCIENT_DEBRIS, occupied, min_x, min_y, max_x, max_y
            )
            return

        asteroid_field_chance = min(
            1.0,
            float(ANOMALY_SPAWN_CHANCE_PER_YEAR) * multiplier * float(ASTEROID_FIELD_SPAWN_SHARE),
        )
        if random.random() < asteroid_field_chance:
            self._spawn_special_salvage(
                Salvage.TYPE_ASTEROID_FIELD, occupied, min_x, min_y, max_x, max_y
            )
            return

        max_allowed = max(1, int(round(star_count * ANOMALY_MAX_STAR_RATIO)))
        current = int(Anomaly.objects.filter(game=self.game).count())
        chance = min(
            1.0,
            anomaly_spawn_chance(
                current, max_allowed, empty_map_chance=ANOMALY_EMPTY_MAP_SPAWN_CHANCE
            ) * multiplier,
        )
        if chance <= 0.0 or random.random() >= chance:
            return
        if current >= max_allowed:
            return
        point = self._random_empty_spawn_point(occupied, min_x, min_y, max_x, max_y)
        if point is None:
            return
        x, y = point
        anomaly_type = random.choice([
            Anomaly.TYPE_NEBULA,
            Anomaly.TYPE_COMET,
            Anomaly.TYPE_RIFT,
            Anomaly.TYPE_BLACK_HOLE,
            Anomaly.TYPE_WORMHOLE,
        ])
        type_labels = {
            Anomaly.TYPE_NEBULA: 'Nebula',
            Anomaly.TYPE_COMET: 'Comet',
            Anomaly.TYPE_RIFT: 'Rift',
            Anomaly.TYPE_BLACK_HOLE: 'Black Hole',
            Anomaly.TYPE_WORMHOLE: 'Wormhole',
        }
        if anomaly_type == Anomaly.TYPE_WORMHOLE:
            if current + 2 > max_allowed:
                return
            name = '%s %s' % (type_labels.get(anomaly_type, 'Anomaly'), current + 1)
            pair_name = '%s %s' % (type_labels.get(anomaly_type, 'Anomaly'), current + 2)
            occupied_with_primary = set(occupied)
            occupied_with_primary.add((x, y))
            pair_point = self._random_empty_spawn_point(
                occupied_with_primary, min_x, min_y, max_x, max_y
            )
            if pair_point is None:
                return
            pair_x, pair_y = pair_point
            a = Anomaly.objects.create(
                game=self.game,
                x=x,
                y=y,
                anomaly_type=anomaly_type,
                name=name,
                heading=random.random() * 360.0,
                stability=random_wormhole_stability_init(),
            )
            b = Anomaly.objects.create(
                game=self.game,
                x=pair_x,
                y=pair_y,
                anomaly_type=anomaly_type,
                name=pair_name,
                heading=random.random() * 360.0,
                stability=random_wormhole_stability_init(),
                wormhole_pair=a,
            )
            a.wormhole_pair = b
            a.save(update_fields=['wormhole_pair'])
            return

        name = '%s %s' % (type_labels.get(anomaly_type, 'Anomaly'), current + 1)
        Anomaly.objects.create(
            game=self.game,
            x=x,
            y=y,
            anomaly_type=anomaly_type,
            name=name,
            heading=random.random() * 360.0,
            stability=random_anomaly_stability_init(),
        )

    def _create_anomaly_message(self, player, text, priority=False):
        from .models import GameMessage
        GameMessage.objects.create(
            game=self.game,
            player=player,
            message=text,
            year=self.game.year,
            category='RANDOM',
            priority=bool(priority),
        )

    def _apply_anomaly_damage(self, fleet, anomaly):
        damage = random.randint(ANOMALY_DAMAGE_MIN, ANOMALY_DAMAGE_MAX)
        danger_level = anomaly_danger_level(anomaly)
        damage = int(round(
            float(damage)
            * damage_intensity_multiplier(danger_level, getattr(anomaly, 'stability', None))
        ))
        damage = max(1, min(100, damage))
        before = int(fleet.integrity or 0)
        fleet.integrity = max(0, before - damage)
        if fleet.integrity <= 0:
            self._apply_anomaly_destruction(
                fleet,
                anomaly,
                reason=(
                    "%s was destroyed by anomaly-induced structural failure at %s."
                    % (fleet.name, format_map_object(anomaly))
                ),
            )
            return
        fleet.save(update_fields=['integrity'])
        text = (
            "%s took %s%% integrity damage whilst exploring %s."
            % (format_map_object(fleet), damage, format_map_object(anomaly))
        )
        self._create_anomaly_message(fleet.player, text, priority=True)

    def _apply_anomaly_cargo_loss(self, fleet, anomaly):
        loss_ratio = random.uniform(ANOMALY_CARGO_LOSS_MIN, ANOMALY_CARGO_LOSS_MAX)
        loss_ratio *= damage_intensity_multiplier(
            anomaly_danger_level(anomaly),
            getattr(anomaly, 'stability', None),
        )
        loss_ratio = min(0.95, max(0.0, loss_ratio))
        iron_loss = int((fleet.ironium_inventory or 0) * loss_ratio)
        bor_loss = int((fleet.boranium_inventory or 0) * loss_ratio)
        germ_loss = int((fleet.germanium_inventory or 0) * loss_ratio)
        res_x_loss = int((fleet.resource_x_inventory or 0) * loss_ratio)
        res_y_loss = int((fleet.resource_y_inventory or 0) * loss_ratio)
        res_z_loss = int((fleet.resource_z_inventory or 0) * loss_ratio)
        colonist_loss = int((fleet.colonists or 0) * loss_ratio)
        fleet.ironium_inventory = max(0, int(fleet.ironium_inventory or 0) - iron_loss)
        fleet.boranium_inventory = max(0, int(fleet.boranium_inventory or 0) - bor_loss)
        fleet.germanium_inventory = max(0, int(fleet.germanium_inventory or 0) - germ_loss)
        fleet.resource_x_inventory = max(0, int(fleet.resource_x_inventory or 0) - res_x_loss)
        fleet.resource_y_inventory = max(0, int(fleet.resource_y_inventory or 0) - res_y_loss)
        fleet.resource_z_inventory = max(0, int(fleet.resource_z_inventory or 0) - res_z_loss)
        fleet.colonists = max(0, int(fleet.colonists or 0) - colonist_loss)
        fleet.save(update_fields=[
            'ironium_inventory', 'boranium_inventory', 'germanium_inventory',
            'resource_x_inventory', 'resource_y_inventory', 'resource_z_inventory',
            'colonists',
        ])
        losses = []
        if iron_loss:
            losses.append('%skt Ironium' % iron_loss)
        if bor_loss:
            losses.append('%skt Boranium' % bor_loss)
        if germ_loss:
            losses.append('%skt Germanium' % germ_loss)
        if res_x_loss:
            losses.append('%skt %s' % (res_x_loss, get_secret_resource_name('resource_x')))
        if res_y_loss:
            losses.append('%skt %s' % (res_y_loss, get_secret_resource_name('resource_y')))
        if res_z_loss:
            losses.append('%skt %s' % (res_z_loss, get_secret_resource_name('resource_z')))
        if colonist_loss:
            losses.append('%sk colonists' % colonist_loss)
        if not losses:
            damage = random.randint(ANOMALY_DAMAGE_MIN, ANOMALY_DAMAGE_MAX)
            damage = int(round(
                float(damage)
                * damage_intensity_multiplier(
                    anomaly_danger_level(anomaly),
                    getattr(anomaly, 'stability', None),
                )
            ))
            damage = max(1, min(100, damage))
            before = int(fleet.integrity or 0)
            fleet.integrity = max(0, before - damage)
            if fleet.integrity <= 0:
                self._apply_anomaly_destruction(
                    fleet,
                    anomaly,
                    reason=(
                        "%s was destroyed after catastrophic hull stress near %s."
                        % (fleet.name, format_map_object(anomaly))
                    ),
                )
                return
            fleet.save(update_fields=['integrity'])
            text = (
                "Anomaly encounter at %s found no cargo on %s; hull stress caused %s%% integrity damage."
                % (format_map_object(anomaly), format_map_object(fleet), damage)
            )
            self._create_anomaly_message(fleet.player, text, priority=True)
            return
        loss_text = ', '.join(losses) if losses else 'no significant cargo'
        text = (
            "Anomaly encounter at %s disrupted %s cargo: %s lost."
            % (format_map_object(anomaly), format_map_object(fleet), loss_text)
        )
        self._create_anomaly_message(fleet.player, text, priority=True)

    def _apply_anomaly_destruction(self, fleet, anomaly, reason=None):
        fleet_name = fleet.name
        player = fleet.player
        fleet.delete()
        if reason:
            text = reason
        else:
            text = (
                "%s was lost whilst exploring %s."
                % (fleet_name, format_map_object(anomaly))
            )
        self._create_anomaly_message(player, text, priority=True)

    def _apply_anomaly_research_boon(
        self, fleet, anomaly, allow_breakthrough=True, reward_tier='medium'
    ):
        player = fleet.player
        rows = ensure_player_research_rows(player)
        if not rows:
            return
        row = random.choice(rows)
        category = row.category
        basic_range = int(getattr(fleet, 'basic_scanner_range', 0) or 0)
        advanced_range = int(getattr(fleet, 'advanced_scanner_range', 0) or 0)
        scanner_multiplier = 1.0
        if advanced_range > 0:
            scanner_multiplier = 1.0
        elif basic_range > 0:
            scanner_multiplier = 0.5
        else:
            scanner_multiplier = 0.2
        danger_level = anomaly_danger_level(anomaly)
        danger_reward_multiplier = reward_intensity_multiplier(
            danger_level,
            getattr(anomaly, 'stability', None),
        )
        if reward_tier == 'low':
            boon_multiplier = 0.6
            text_prefix = 'Minor anomaly data'
        else:
            boon_multiplier = 1.0
            text_prefix = 'Anomaly data'
        breakthrough_chance = {
            DANGER_LOW: 0.01,
            DANGER_MEDIUM: 0.18,
            DANGER_HIGH: 0.25,
        }.get(danger_level, 0.10)
        if allow_breakthrough and random.random() < breakthrough_chance:
            extra_rp = self._convert_secret_resources_to_rp(fleet)
            extra_rp = int(round(float(extra_rp) * danger_reward_multiplier))
            if self._apply_anomaly_breakthrough(player, anomaly):
                if extra_rp > 0:
                    result = apply_research_bonus_rp(player, category.id, int(extra_rp))
                    if result and int(result.get('new_level', 0)) > int(result.get('old_level', 0)):
                        self._create_research_unlock_messages(player, [result])
                return
        if random.random() < 0.5:
            bonus_rp_roll = apply_roll_bend(random.random(), bend=-2.3)
            bonus_rp = ANOMALY_BONUS_RP_MIN + int(round(
                (ANOMALY_BONUS_RP_MAX - ANOMALY_BONUS_RP_MIN) * bonus_rp_roll
            ))
            bonus_rp = int(round(float(bonus_rp) * danger_reward_multiplier))
            bonus_rp = int(round(float(bonus_rp) * scanner_multiplier))
            bonus_rp = int(round(float(bonus_rp) * boon_multiplier))
            extra_rp = self._convert_secret_resources_to_rp(fleet)
            extra_rp = int(round(float(extra_rp) * danger_reward_multiplier))
            extra_rp = int(round(float(extra_rp) * boon_multiplier))
            total_rp = int(bonus_rp) + int(extra_rp)
            result = apply_research_bonus_rp(player, category.id, total_rp)
            text = (
                "%s from %s granted %s bonus RP in %s."
                % (text_prefix, format_map_object(anomaly), bonus_rp, category.name)
            )
            if extra_rp > 0:
                text += " Exotic cargo yielded %s RP." % int(extra_rp)
            if result and int(result.get('new_level', 0)) > int(result.get('old_level', 0)):
                text += " Level increased to %s." % int(result['new_level'])
            self._create_anomaly_message(player, text, priority=False)
            return
        bonus_rp_roll = apply_roll_bend(random.random(), bend=-2.3)
        bonus_rp = ANOMALY_BONUS_RP_MIN + int(round(
            (ANOMALY_BONUS_RP_MAX - ANOMALY_BONUS_RP_MIN) * bonus_rp_roll
        ))
        bonus_rp = int(round(float(bonus_rp) * danger_reward_multiplier))
        bonus_rp = int(round(float(bonus_rp) * scanner_multiplier))
        bonus_rp = int(round(float(bonus_rp) * boon_multiplier))
        extra_rp = self._convert_secret_resources_to_rp(fleet)
        extra_rp = int(round(float(extra_rp) * danger_reward_multiplier))
        extra_rp = int(round(float(extra_rp) * boon_multiplier))
        total_rp = int(bonus_rp) + int(extra_rp)
        result = apply_research_bonus_rp(player, category.id, total_rp)
        text = (
            "%s from %s granted %s bonus RP in %s."
            % (text_prefix, format_map_object(anomaly), bonus_rp, category.name)
        )
        if extra_rp > 0:
            text += " Exotic cargo yielded %s RP." % int(extra_rp)
        if result and int(result.get('new_level', 0)) > int(result.get('old_level', 0)):
            text += " Level increased to %s." % int(result['new_level'])
        self._create_anomaly_message(player, text, priority=False)

    @staticmethod
    def _convert_secret_resources_to_rp(fleet):
        rates = {
            'resource_x': 2,
            'resource_y': 3,
            'resource_z': 4,
        }
        extra_rp = 0
        update_fields = []
        for key, rate in rates.items():
            amount = int(getattr(fleet, f'{key}_inventory', 0) or 0)
            if amount <= 0:
                continue
            extra_rp += amount * int(rate)
            setattr(fleet, f'{key}_inventory', 0)
            update_fields.append(f'{key}_inventory')
        if update_fields:
            fleet.save(update_fields=update_fields)
        return int(extra_rp)

    def _apply_wormhole_interaction(self, fleet, anomaly):
        """Resolve wormhole transit: possible damage, then relocation near the paired endpoint."""
        from .models import Anomaly, Report

        endpoint = anomaly
        pair = getattr(endpoint, 'wormhole_pair', None)
        if not pair or not Anomaly.objects.filter(id=pair.id).exists():
            return
        if pair.id == endpoint.id:
            return
        pair = Anomaly.objects.get(id=pair.id)
        first_traversal = not self._has_player_traversed_wormhole(
            fleet.player, endpoint, pair
        )

        stability = self._anomaly_stability(endpoint)
        danger_level = anomaly_danger_level(endpoint)
        danger_mult = damage_intensity_multiplier(danger_level, stability)
        if stability < 30:
            destruction_chance = (
                (30.0 - float(stability)) / 30.0
            ) * float(WORMHOLE_INSTANT_DESTRUCTION_MAX_CHANCE) * float(danger_mult)
            if random.random() < destruction_chance:
                fleet_name = fleet.name
                player = fleet.player
                fleet.delete()
                text = (
                    "%s was destroyed in catastrophic wormhole transit through %s."
                    % (fleet_name, format_map_object(endpoint))
                )
                self._create_anomaly_message(player, text, priority=True)
                return

        instability = self._anomaly_instability_ratio(endpoint)
        damage_chance = max(0.0, min(1.0, float(instability) * float(danger_mult)))
        took_damage = False
        damage = 0
        if random.random() < damage_chance:
            max_damage = max(
                1,
                int(round(
                    float(WORMHOLE_DAMAGE_MAX) *
                    float(instability) *
                    float(danger_mult)
                )),
            )
            damage = random.randint(1, max_damage)
            fleet.integrity = max(0, int(fleet.integrity or 0) - int(damage))
            took_damage = damage > 0
            if fleet.integrity <= 0:
                self._apply_anomaly_destruction(fleet, endpoint)
                return

        exit_x, exit_y = self._find_wormhole_exit(pair, endpoint)
        fleet.x = int(exit_x)
        fleet.y = int(exit_y)
        if took_damage:
            fleet.save(update_fields=['integrity', 'x', 'y'])
        else:
            fleet.save(update_fields=['x', 'y'])

        self._create_or_update_report(fleet.player, 'anomaly', endpoint, self.game.year)
        self._create_or_update_report(fleet.player, 'anomaly', pair, self.game.year)
        self._mark_player_wormhole_traversed(
            fleet.player, endpoint, pair, self.game.year
        )

        if took_damage or first_traversal:
            fleet_label = format_map_object(fleet)
            endpoint_label = format_map_object(endpoint)
            pair_label = format_map_object(pair)
            exit_label = map_coordinate_link(
                self.game, exit_x, exit_y, label='(%s, %s)' % (int(exit_x), int(exit_y))
            )
            if took_damage:
                text = (
                    "%s traversed wormhole %s, suffered %s%% integrity damage, "
                    "and emerged from %s at %s."
                    % (fleet_label, endpoint_label, damage, pair_label, exit_label)
                )
            else:
                text = (
                    "%s traversed wormhole %s and emerged from %s at %s."
                    % (fleet_label, endpoint_label, pair_label, exit_label)
                )
            self._create_anomaly_message(fleet.player, text, priority=False)

    def _has_player_traversed_wormhole(self, player, endpoint, pair):
        """Return True if the player has already traversed this wormhole pair."""
        from .models import Report

        anomaly_ids = [getattr(endpoint, 'id', None), getattr(pair, 'id', None)]
        reports = Report.objects.filter(
            player=player,
            target_type='anomaly',
            target_id__in=[anomaly_id for anomaly_id in anomaly_ids if anomaly_id],
        )
        for report in reports:
            data = report.get_report_data()
            if bool(data.get('wormhole_traversed')):
                return True
        return False

    def _mark_player_wormhole_traversed(self, player, endpoint, pair, year):
        """Persist traversal state for both endpoints of a wormhole pair."""
        from .models import Report

        anomaly_ids = [getattr(endpoint, 'id', None), getattr(pair, 'id', None)]
        reports = Report.objects.filter(
            player=player,
            target_type='anomaly',
            target_id__in=[anomaly_id for anomaly_id in anomaly_ids if anomaly_id],
        )
        for report in reports:
            data = report.get_report_data()
            if bool(data.get('wormhole_traversed')):
                continue
            data['wormhole_traversed'] = True
            data['first_wormhole_traversal_year'] = int(year)
            report.set_report_data(data)
            report.save(update_fields=['cached_report'])

    def _calculate_next_generation(self):
        """Calculate next generation time based on turn scheme."""
        interval = TURN_INTERVALS.get(self.game.turn_scheme)
        return timezone.now() + interval if interval else None

    def _reset_turn_ins(self):
        """Reset turned_in status and update message visibility for all players."""
        for player in self.game.players.filter(defeated=False):
            player.turned_in = False
            player.messages_seen_year = player.last_seen_year
            player.save(update_fields=['turned_in', 'messages_seen_year'])

    def generate_reports(self):
        """Generate exploration reports for all fleets at their current locations."""
        from .models import Fleet
        for fleet in Fleet.objects.filter(game=self.game, player__isnull=False, player__defeated=False):
            self._generate_reports_for_fleet(fleet)

    def generate_shared_intel_reports(self):
        """Push allied intel reports to players that are granted sharing."""
        from .models import Fleet, Player, Star

        players = list(Player.objects.filter(game=self.game, defeated=False))
        if len(players) < 2:
            return

        fleets_by_player = {
            player.id: list(Fleet.objects.filter(game=self.game, player=player))
            for player in players
        }
        stars_by_player = {
            player.id: list(Star.objects.filter(game=self.game, player=player))
            for player in players
        }

        for viewer in players:
            for grantor in players:
                if viewer.id == grantor.id:
                    continue
                if not player_grants_permission(
                    grantor,
                    viewer,
                    PERMISSION_SHARE_INTEL,
                    stance_map=self._stance_map_for_player(grantor),
                ):
                    continue
                colony_report_tier = shared_colony_report_policy(
                    grantor,
                    viewer,
                    stance_map=self._stance_map_for_player(grantor),
                )
                fleet_report_tier, fleet_include_cargo = shared_fleet_report_policy(
                    grantor,
                    viewer,
                    stance_map=self._stance_map_for_player(grantor),
                )
                for star in stars_by_player.get(grantor.id, []):
                    self._create_or_update_report(
                        viewer,
                        'star',
                        star,
                        self.game.year,
                        report_tier=colony_report_tier,
                        conceal_secret_resources=True,
                    )
                for fleet in fleets_by_player.get(grantor.id, []):
                    if (
                        fleet_is_cloaked(fleet) and
                        not player_reveals_cloaked_fleets(grantor, viewer)
                    ):
                        continue
                    self._create_or_update_report(
                        viewer,
                        'fleet',
                        fleet,
                        self.game.year,
                        report_tier=fleet_report_tier,
                        include_cargo=fleet_include_cargo,
                    )

    def generate_scanner_reports(self):
        """Generate scanner-based reports for stars and fleets within sensor range."""
        from .models import Star, Fleet, Salvage, Anomaly

        for player in self.game.players.filter(defeated=False):
            colony_positions = set(player.stars.values_list('x', 'y'))
            if not colony_positions:
                continue
            for fleet in Fleet.objects.filter(game=self.game).exclude(player=player):
                if (fleet.x, fleet.y) not in colony_positions:
                    continue
                self._create_or_update_report(
                    player,
                    'fleet',
                    fleet,
                    self.game.year,
                    report_tier='encounter',
                    include_cargo=True,
                )

        if getattr(self.game, 'no_scanners', False):
            return

        for player in self.game.players.filter(defeated=False):
            sources = get_scanner_sources_for_player(self.game, player)
            if not sources:
                continue
            owned_sources = get_owned_scanner_sources_for_player(self.game, player)

            colony_positions = set(player.stars.values_list('x', 'y'))
            player_fleet_positions = set(
                player.fleets.values_list('x', 'y')
            )
            habitable_stars_found = []
            has_basic = any(int(src.get('basic') or 0) > 0 for src in sources)
            has_advanced = any(int(src.get('advanced') or 0) > 0 for src in sources)
            if not has_basic and not has_advanced:
                continue

            # Stars: advanced reports override basic reports.
            for star in Star.objects.filter(game=self.game):
                if star.player_id == player.id:
                    continue
                if has_advanced and position_in_scanner_range(
                    star.x, star.y, sources, range_key='advanced'
                ):
                    conceal_secret_resources = not position_in_scanner_range(
                        star.x, star.y, owned_sources, range_key='advanced'
                    )
                    created = self._create_or_update_report(
                        player,
                        'star',
                        star,
                        self.game.year,
                        report_tier='advanced',
                        conceal_secret_resources=conceal_secret_resources,
                    )
                    self._queue_scanner_habitable_star(
                        habitable_stars_found,
                        player,
                        star,
                        created,
                        player_fleet_positions,
                    )
                    continue
                if has_basic and position_in_scanner_range(
                    star.x, star.y, sources, range_key='basic'
                ):
                    created = self._create_or_update_report(
                        player, 'star', star, self.game.year, report_tier='basic'
                    )
                    self._queue_scanner_habitable_star(
                        habitable_stars_found,
                        player,
                        star,
                        created,
                        player_fleet_positions,
                    )

            # Fleets: basic scans confirm presence, advanced scans reveal composition.
            for fleet in Fleet.objects.filter(game=self.game).exclude(player=player):
                if (fleet.x, fleet.y) in colony_positions:
                    continue
                cloaked = fleet_is_cloaked(fleet)
                if has_advanced and position_in_scanner_range(
                    fleet.x, fleet.y, sources, range_key='advanced'
                ):
                    if cloaked and bool(getattr(fleet, 'advanced_cloak', False)):
                        continue
                    self._create_or_update_report(
                        player, 'fleet', fleet, self.game.year, report_tier='advanced'
                    )
                    continue
                if has_basic and position_in_scanner_range(
                    fleet.x, fleet.y, sources, range_key='basic'
                ):
                    if cloaked:
                        continue
                    self._create_or_update_report(
                        player, 'fleet', fleet, self.game.year, report_tier='basic'
                    )

            # Salvage and anomalies: basic scans confirm identity; advanced scans reveal detail.
            for salvage in Salvage.objects.filter(game=self.game):
                if has_advanced and position_in_scanner_range(
                    salvage.x, salvage.y, sources, range_key='advanced'
                ):
                    self._create_or_update_report(
                        player, 'salvage', salvage, self.game.year, report_tier='advanced'
                    )
                    continue
                if has_basic and position_in_scanner_range(
                    salvage.x, salvage.y, sources, range_key='basic'
                ):
                    self._create_or_update_report(
                        player, 'salvage', salvage, self.game.year, report_tier='basic'
                    )
            for anomaly in Anomaly.objects.filter(game=self.game):
                if has_advanced and position_in_scanner_range(
                    anomaly.x, anomaly.y, sources, range_key='advanced'
                ):
                    self._create_or_update_report(
                        player, 'anomaly', anomaly, self.game.year, report_tier='advanced'
                    )
                    continue
                if has_basic and position_in_scanner_range(
                    anomaly.x, anomaly.y, sources, range_key='basic'
                ):
                    self._create_or_update_report(
                        player, 'anomaly', anomaly, self.game.year, report_tier='basic'
                    )
            self._send_scanner_habitable_world_rollup(
                player, habitable_stars_found
            )

    def _generate_reports_for_fleet(self, fleet):
        """Generate reports for all objects at fleet's location."""
        from .models import Star, Salvage, Fleet, Anomaly

        x, y = fleet.x, fleet.y
        player = fleet.player
        year = self.game.year
        report_tier = self._report_tier_for_visit(fleet)
        include_cargo = self._player_has_advanced_scanner_at(player, x, y)

        # Report on all stars at this location
        for star in Star.objects.filter(game=self.game, x=x, y=y):
            self._discover_secret_resources_from_star(player, star, fleet=fleet)
            self._create_or_update_report(player, 'star', star, year, report_tier=report_tier)

        # Report on other players' fleets at this location
        for other_fleet in Fleet.objects.filter(
            game=self.game, x=x, y=y
        ).exclude(player=player):
            self._create_or_update_report(
                player,
                'fleet',
                other_fleet,
                year,
                report_tier=report_tier,
                include_cargo=include_cargo,
            )

        # Report on all salvage at this location
        for salvage in Salvage.objects.filter(game=self.game, x=x, y=y):
            self._create_or_update_report(player, 'salvage', salvage, year, report_tier=report_tier)

        for anomaly in Anomaly.objects.filter(game=self.game, x=x, y=y):
            self._create_or_update_report(player, 'anomaly', anomaly, year, report_tier=report_tier)

    def _create_or_update_report(
        self,
        player,
        target_type,
        obj,
        year,
        report_tier='advanced',
        include_cargo=False,
        conceal_secret_resources=False,
    ):
        """Create or update a report for an object."""
        from .models import Report, Fleet
        from .messages import HabitableWorldMessageFactory

        report = Report.objects.filter(
            player=player,
            target_type=target_type,
            target_id=obj.id,
        ).first()
        existing_owner_known = False

        if report:
            existing_data = report.get_report_data()
            existing_owner_known = bool(existing_data.get('player_name'))
            existing_tier = existing_data.get('report_tier') or 'advanced'
            report.year = year
            report.game = self.game
            fresh_data = self._build_report_data(
                player,
                obj,
                target_type,
                report_tier=report_tier,
                include_cargo=include_cargo,
            )
            if conceal_secret_resources:
                fresh_data = self._conceal_report_secret_resources(
                    player,
                    target_type,
                    fresh_data,
                )
            if self._report_tier_rank(existing_tier) > self._report_tier_rank(report_tier):
                report_data = self._merge_report_refresh(
                    target_type,
                    existing_data,
                    fresh_data,
                    existing_tier,
                    report_tier,
                )
            else:
                report_data = fresh_data
            if existing_data.get('wormhole_traversed'):
                report_data['wormhole_traversed'] = True
                if 'first_wormhole_traversal_year' in existing_data:
                    report_data['first_wormhole_traversal_year'] = (
                        existing_data.get('first_wormhole_traversal_year')
                    )
            report.set_report_data(report_data)
            report.save()
            created = False
        else:
            existing_data = {}
            report_data = self._build_report_data(
                player,
                obj,
                target_type,
                report_tier=report_tier,
                include_cargo=include_cargo,
            )
            if conceal_secret_resources:
                report_data = self._conceal_report_secret_resources(
                    player,
                    target_type,
                    report_data,
                )
            report = Report.objects.create(
                player=player,
                target_type=target_type,
                target_id=obj.id,
                game=self.game,
                year=year,
                cached_report='{}',
            )
            report.set_report_data(report_data)
            report.save()
            created = True

        if target_type == 'star':
            old_unknown = list((existing_data or {}).get('unknown_secret_resources') or [])
            new_unknown = list((report_data or {}).get('unknown_secret_resources') or [])
            if (
                self._report_tier_rank(report_tier) >= self._report_tier_rank('advanced') and
                new_unknown and
                any(key not in old_unknown for key in new_unknown)
            ):
                self._send_unexplained_scan_contact_message(player, obj, 'star')

        owner_now_known = bool(report_data.get('player_name'))
        if (
            target_type in ('star', 'fleet') and
            owner_now_known and
            not existing_owner_known
        ):
            self._send_first_contact_message(
                player,
                target_type,
                obj,
                exclude_target=(target_type, obj.id),
            )

        if created and target_type == 'star' and calculate_habitability_factor(player, obj) >= 0 and obj.player != player:
            fleet = Fleet.objects.filter(game=self.game, player=player, x=obj.x, y=obj.y).first()
            if fleet:
                factory = HabitableWorldMessageFactory(self.game, player, fleet, obj)
                msg = factory.new_message()
                msg.year = self.game.year
                msg.save()
        return created

    def _merge_report_refresh(self, target_type, existing_data, fresh_data, existing_tier, fresh_tier):
        merged = dict(existing_data or {})
        for key, value in fresh_data.items():
            if key == 'report_tier':
                continue
            if value is None and key in merged:
                continue
            merged[key] = value
        merged['report_tier'] = existing_tier

        if target_type == 'fleet' and fresh_tier == 'basic' and existing_data.get('name'):
            merged['name'] = existing_data.get('name')
            if existing_data.get('player_name'):
                merged['player_name'] = existing_data.get('player_name')

        if target_type == 'salvage':
            if fresh_tier == 'basic' and existing_data.get('name'):
                merged['name'] = existing_data.get('name')
            if existing_data.get('salvage_type') and not fresh_data.get('salvage_type'):
                merged['salvage_type'] = existing_data.get('salvage_type')

        return merged

    def _queue_scanner_habitable_star(
        self,
        habitable_stars_found,
        player,
        star,
        created,
        player_fleet_positions,
    ):
        if not created or not player or not star:
            return
        if star.player_id == player.id:
            return
        if (star.x, star.y) in player_fleet_positions:
            return
        if calculate_habitability_factor(player, star) < 0:
            return
        habitable_stars_found.append(star)

    def _send_scanner_habitable_world_rollup(self, player, stars):
        if not player or not stars:
            return
        factory = ScannerHabitableWorldRollupMessageFactory(
            self.game,
            player,
            stars,
        )
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def _mark_secret_resource_discovered(self, player, resource_key, star=None, fleet=None, source=None):
        if not player:
            return False
        player_field = f'discovered_{resource_key}'
        account_field = f'discovered_{resource_key}'
        player_discovered = bool(getattr(player, player_field, False))
        account = getattr(player, 'account', None)
        account_discovered = bool(getattr(account, account_field, False)) if account else False

        if not player_discovered:
            setattr(player, player_field, True)
            player.save(update_fields=[player_field])
        if account and not account_discovered:
            setattr(account, account_field, True)
            account.save(update_fields=[account_field])

        discovery_location = source or star or fleet
        if not player_discovered and discovery_location is not None:
            factory = SecretResourceDiscoveryMessageFactory(
                self.game,
                player,
                star=discovery_location,
                resource_name=get_secret_resource_name(resource_key),
                fleet=fleet,
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()
        return not player_discovered

    def _discover_secret_resources_from_star(self, player, star, fleet=None):
        if not player or not star:
            return
        for key in SECRET_RESOURCE_KEYS:
            if int(getattr(star, f'{key}_yield', 0) or 0) > 0 or int(getattr(star, f'{key}_inventory', 0) or 0) > 0:
                self._mark_secret_resource_discovered(player, key, star=star, fleet=fleet)

    def _unknown_secret_resource_keys_for_star(self, player, star):
        if not player or not star:
            return []
        unknown = []
        for key in SECRET_RESOURCE_KEYS:
            amount_present = (
                int(getattr(star, '%s_yield' % key, 0) or 0) > 0 or
                int(getattr(star, '%s_inventory' % key, 0) or 0) > 0
            )
            if not amount_present:
                continue
            if not bool(getattr(player, 'discovered_%s' % key, False)):
                unknown.append(key)
        return unknown

    def _conceal_report_secret_resources(self, player, target_type, report_data):
        """Hide secret-resource identity in non-local star intel sharing."""
        data = dict(report_data or {})
        if target_type != 'star':
            return data
        unknown = list(data.get('unknown_secret_resources') or [])
        for key in SECRET_RESOURCE_KEYS:
            if bool(getattr(player, 'discovered_%s' % key, False)):
                continue
            yield_key = '%s_yield' % key
            inventory_key = '%s_inventory' % key
            present = (
                int(data.get(yield_key, 0) or 0) > 0 or
                int(data.get(inventory_key, 0) or 0) > 0 or
                key in unknown
            )
            if not present:
                continue
            if key not in unknown:
                unknown.append(key)
        data['unknown_secret_resources'] = unknown
        return data

    def _send_unexplained_scan_contact_message(self, player, obj, target_type):
        if not player or obj is None:
            return
        if target_type == 'star':
            subject = 'traces of an unexplained material'
            target_label = None
        else:
            return
        factory = UnexplainedScanContactMessageFactory(
            self.game,
            player,
            target=obj,
            subject=subject,
            target_label=target_label,
        )
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def _discover_secret_resources_from_fleet(self, player, fleet):
        if not player or not fleet:
            return
        for key in SECRET_RESOURCE_KEYS:
            if int(getattr(fleet, f'{key}_inventory', 0) or 0) > 0:
                self._mark_secret_resource_discovered(player, key, star=None, fleet=fleet)

    def _fleet_motion_snapshot(self, fleet):
        """Return (travel_warp, warp_advantage, heading_degrees) for fleet reports."""
        if not hasattr(self, '_fleet_motion_cache'):
            self._fleet_motion_cache = {}
        cached = self._fleet_motion_cache.get(fleet.id)
        if cached is not None:
            return cached

        heading = 0.0
        try:
            heading = float(getattr(fleet, 'heading', 0.0) or 0.0) % 360.0
        except (TypeError, ValueError):
            heading = 0.0

        try:
            travel_warp = max(0, int(getattr(fleet, 'travel_warp', 0) or 0))
        except (TypeError, ValueError):
            travel_warp = 0

        try:
            warp_advantage = float(getattr(fleet, 'warp_advantage', 0.0) or 0.0)
        except (TypeError, ValueError):
            warp_advantage = 0.0

        snapshot = (travel_warp, warp_advantage, heading)
        self._fleet_motion_cache[fleet.id] = snapshot
        return snapshot

    def _build_report_data(self, player, obj, target_type, report_tier='advanced', include_cargo=False):
        """Build the data dict to cache in a report."""
        if target_type == 'star':
            unknown_secret_resources = self._unknown_secret_resource_keys_for_star(player, obj)
            base = {
                'name': obj.name,
                'x': obj.x,
                'y': obj.y,
                'report_tier': report_tier,
                'unknown_secret_resources': unknown_secret_resources,
            }
            if report_tier == 'ownership':
                base['player_name'] = obj.player.name if obj.player else None
                return base
            base.update({
                'gravity': obj.gravity,
                'temperature': obj.temperature,
                'radiation': obj.radiation,
            })
            if report_tier == 'basic':
                base.update({
                    'capacity': effective_capacity(player, obj),
                    'is_survivable': calculate_habitability_factor(player, obj) >= 0,
                })
                return base
            base.update({
                'colonists': obj.colonists,
                'capacity': effective_capacity(player, obj),
                'is_survivable': calculate_habitability_factor(player, obj) >= 0,
                'player_name': obj.player.name if obj.player else None,
                'ironium_yield': obj.ironium_yield,
                'boranium_yield': obj.boranium_yield,
                'germanium_yield': obj.germanium_yield,
                'resource_x_yield': obj.resource_x_yield,
                'resource_y_yield': obj.resource_y_yield,
                'resource_z_yield': obj.resource_z_yield,
                'ironium_inventory': obj.ironium_inventory,
                'boranium_inventory': obj.boranium_inventory,
                'germanium_inventory': obj.germanium_inventory,
                'resource_x_inventory': obj.resource_x_inventory,
                'resource_y_inventory': obj.resource_y_inventory,
                'resource_z_inventory': obj.resource_z_inventory,
            })
            if report_tier == 'encounter':
                scanner_basic = 0
                scanner_advanced = 0
                if obj.player:
                    scanner_basic, scanner_advanced = get_player_colony_scanner_ranges(
                        obj.player
                    )
                jobs = calculate_total_jobs(obj)
                employment = calculate_employment_percent(obj)
                base.update({
                    # Infrastructure snapshot (matches visible Detail panel values).
                    'mines': obj.mines,
                    'factories': obj.factories,
                    'factories_bp': calculate_available_buildpoints(obj),
                    'labs': obj.labs,
                    'labs_rp': calculate_available_researchpoints(obj),
                    'basic_scanner_range': scanner_basic,
                    'advanced_scanner_range': scanner_advanced,
                    'defenses': obj.defenses,
                    'defenses_tooltip': None,
                    'shipyards': obj.shipyards,
                    'has_dyson_sphere': bool(getattr(obj, 'has_dyson_sphere', False)),
                    'jobs_count': jobs,
                    'jobs_employment': employment,
                })
            return base
        elif target_type == 'fleet':
            travel_warp, warp_advantage, heading = self._fleet_motion_snapshot(obj)
            data = {
                'name': (
                    format_basic_unknown_fleet_name(obj)
                    if report_tier == 'basic' else obj.name
                ),
                'x': obj.x,
                'y': obj.y,
                'report_tier': report_tier,
                'travel_warp': travel_warp,
                'warp_advantage': warp_advantage,
                'heading': heading,
                'is_cloaked': fleet_is_cloaked(obj),
            }
            if report_tier == 'ownership':
                data['player_name'] = obj.player.name if obj.player else 'Abandoned'
                return data
            if report_tier == 'basic':
                return data
            data.update({
                'player_name': obj.player.name if obj.player else 'Abandoned',
                'ship_count': obj.ship_count,
                'integrity': obj.integrity,
            })
            if include_cargo:
                data.update({
                    'cargo_capacity': getattr(obj, 'cargo_capacity', None),
                    'cargo_used': getattr(obj, 'cargo_used', None),
                    'cargo_remaining': getattr(obj, 'cargo_remaining', None),
                    'fuel': getattr(obj, 'fuel', None),
                    'max_fuel': getattr(obj, 'max_fuel', None),
                    'ironium_inventory': getattr(obj, 'ironium_inventory', None),
                    'boranium_inventory': getattr(obj, 'boranium_inventory', None),
                    'germanium_inventory': getattr(obj, 'germanium_inventory', None),
                    'resource_x_inventory': getattr(obj, 'resource_x_inventory', None),
                    'resource_y_inventory': getattr(obj, 'resource_y_inventory', None),
                    'resource_z_inventory': getattr(obj, 'resource_z_inventory', None),
                    'colonists': getattr(obj, 'colonists', None),
                })
            if report_tier == 'encounter' and include_cargo:
                offense_mod = int(round(float(obj.offense_level) * 10.0))
                defense_mod = int(round(float(obj.defense_level) * 10.0))
                data.update({
                    'max_safe_warp': obj.max_safe_warp,
                    'offense_modifier': f'{offense_mod:+d}',
                    'defense_modifier': f'{defense_mod:+d}',
                    'has_bombs': obj.has_bombs,
                    'has_miners': obj.has_miners,
                    'has_fuel_factory': bool(obj.has_fuel_factory),
                    'fuel_factory_mg_per_year': getattr(
                        obj, 'fuel_factory_mg_per_year', 0.0
                    ),
                    'fuel_factory_max_warp': getattr(
                        obj, 'fuel_factory_max_warp', -1
                    ),
                    'has_wormhole_drive': bool(obj.has_wormhole_drive),
                    'max_cloaked_warp': getattr(obj, 'max_cloaked_warp', -1),
                    'advanced_cloak': bool(getattr(obj, 'advanced_cloak', False)),
                    'basic_scanner_range': getattr(obj, 'basic_scanner_range', 0),
                    'advanced_scanner_range': getattr(obj, 'advanced_scanner_range', 0),
                })
            return data
        elif target_type == 'salvage':
            if report_tier == 'ownership':
                data = {
                    'name': obj.name,
                    'x': obj.x,
                    'y': obj.y,
                    'salvage_type': obj.salvage_type,
                    'total_minerals': obj.total_minerals,
                    'report_tier': report_tier,
                }
                return data
            if report_tier == 'basic' and not getattr(self.game, 'no_scanners', False):
                salvage_type = obj.salvage_type
                if salvage_type == 'ANCIENT_DEBRIS':
                    salvage_type = None
                data = {
                    'name': format_basic_hidden_salvage_name(obj),
                    'x': obj.x,
                    'y': obj.y,
                    'salvage_type': salvage_type,
                    'total_minerals': obj.total_minerals,
                    'report_tier': report_tier,
                }
                return data
            return {
                'name': obj.name,
                'x': obj.x,
                'y': obj.y,
                'salvage_type': obj.salvage_type,
                'danger_level': salvage_danger_level(obj),
                'ironium_inventory': obj.ironium_inventory,
                'boranium_inventory': obj.boranium_inventory,
                'germanium_inventory': obj.germanium_inventory,
                'resource_x_inventory': obj.resource_x_inventory,
                'resource_y_inventory': obj.resource_y_inventory,
                'resource_z_inventory': obj.resource_z_inventory,
                'total_minerals': obj.total_minerals,
                'report_tier': report_tier,
            }
        elif target_type == 'anomaly':
            if report_tier in ('ownership', 'basic'):
                data = {
                    'name': obj.name,
                    'x': obj.x,
                    'y': obj.y,
                    'report_tier': report_tier,
                }
                if report_tier == 'basic':
                    data['anomaly_type'] = obj.anomaly_type
                return data
            return {
                'name': obj.name,
                'x': obj.x,
                'y': obj.y,
                'anomaly_type': obj.anomaly_type,
                'danger_level': anomaly_danger_level(obj),
                'description': obj.description,
                'heading': obj.heading,
                'stability': obj.stability,
                'wormhole_pair_short_id': (
                    obj.wormhole_pair.short_id if getattr(obj, 'wormhole_pair', None) else None
                ),
                'report_tier': report_tier,
            }
        return {}

    def _report_tier_for_visit(self, fleet):
        """Return report tier for a fleet visit based on scanner settings."""
        if not getattr(self.game, 'no_scanners', False):
            return 'encounter'
        try:
            basic = int(getattr(fleet, 'basic_scanner_range', 0) or 0)
        except (TypeError, ValueError):
            basic = 0
        try:
            advanced = int(getattr(fleet, 'advanced_scanner_range', 0) or 0)
        except (TypeError, ValueError):
            advanced = 0
        if advanced > 20:
            return 'encounter'
        if advanced > 0:
            return 'advanced'
        if basic > 0:
            return 'basic'
        return 'ownership'

    def _report_tier_rank(self, tier):
        """Higher numbers mean more detailed reports."""
        order = {
            'ownership': 0,
            'basic': 1,
            'advanced': 2,
            'encounter': 3,
        }
        return order.get(str(tier or '').lower(), 2)

    def _player_has_advanced_scanner_at(self, player, x, y):
        """Return True if player has any advanced scanners at the location."""
        if not player:
            return False
        if getattr(self.game, 'no_scanners', False):
            return False
        sources = self._scanner_sources_by_player_id.get(player.id)
        if sources is None:
            sources = get_scanner_sources_for_player(self.game, player)
            self._scanner_sources_by_player_id[player.id] = sources
        return position_in_scanner_range(x, y, sources, range_key='advanced')

    def _update_ai_checkin_state(self, auto_turn_in=False):
        """Refresh AI check-in bookkeeping and optional quorum auto-ready state."""
        interval = max(1, int(get_ai_check_in_turns() or 1))
        current_year = int(self.game.year or 0)
        for player in self.game.players.filter(defeated=False, is_ai=True):
            update_fields = []
            if auto_turn_in and not bool(getattr(player, 'turned_in', False)):
                player.turned_in = True
                update_fields.append('turned_in')
            last_checkin = getattr(player, 'ai_last_checkin_year', None)
            if (
                last_checkin is None or
                (current_year - int(last_checkin or 0)) >= interval
            ):
                player.ai_last_checkin_year = current_year
                update_fields.append('ai_last_checkin_year')
            if update_fields:
                player.save(update_fields=update_fields)

    def check_quorum(self):
        """Check if all players have turned in. Returns True if quorum met."""
        if self.game.turn_scheme != 'QUORUM':
            return False
        self._update_ai_checkin_state(auto_turn_in=True)
        total = self.game.players.filter(defeated=False).count()
        turned_in = self.game.players.filter(turned_in=True, defeated=False).count()
        return total > 0 and turned_in == total

    def generate_turns(self, turns):
        """Generate multiple turns for the game."""
        for _ in range(turns):
            self.generate_turn()

    def fleet_movements(self):
        """Move fleets according to their orders."""
        self._locked_fleet_ids_for_year = set()
        self._ambush_fleet_ids_for_year = set()
        self._fleet_start_positions_for_year = {
            fleet.id: (fleet.x, fleet.y) for fleet in self.game.fleets.all()
        }
        # Get fleet IDs first, then fetch fresh for each processing
        # This ensures we see changes made by other fleet's transfers
        fleet_ids = list(self.game.fleets.order_by('id').values_list('id', flat=True))
        random.shuffle(fleet_ids)
        for fleet_id in fleet_ids:
            try:
                fleet = self.game.fleets.get(id=fleet_id)
            except self.game.fleets.model.DoesNotExist:
                continue  # Fleet was deleted (e.g., by colonise order)
            if fleet.player is None or bool(getattr(fleet.player, 'defeated', False)):
                continue
            # Reset yearly motion snapshot; movement handlers set this when travel occurs.
            fleet.travel_warp = 0
            if fleet.id in self._locked_fleet_ids_for_year:
                fleet.save()
                continue
            result = self.move_fleet(fleet)
            if result is not None:
                result.save()

    def check_lost_fleets(self):
        """Remove fleets that have moved beyond map boundaries."""
        max_x = self.game.map_size_x
        max_y = self.game.map_size_y
        for fleet in self.game.fleets.all():
            if fleet.x < 0 or fleet.x >= max_x or fleet.y < 0 or fleet.y >= max_y:
                if fleet.player is not None:
                    self._create_fleet_lost_message(fleet)
                fleet.delete()

    def _create_fleet_lost_message(self, fleet):
        """Create a message for a fleet lost beyond map boundaries."""
        if fleet.player is None:
            return
        factory = FleetLostMessageFactory(self.game, fleet.player, fleet.name)
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def check_damaged_fleets(self):
        """Destroy any fleets with zero integrity."""
        for fleet in self.game.fleets.filter(integrity__lte=0):
            if fleet.player is None:
                fleet.delete()
                continue
            self._handle_warp_destruction(fleet, warp_speed=0, from_damage=True)

    def resolve_combat(self):
        """Resolve combat at any location with fleets from 2+ players."""
        from .models import Fleet
        fleets = list(Fleet.objects.filter(game=self.game, player__isnull=False, player__defeated=False))
        locations = {}
        for fleet in fleets:
            locations.setdefault((fleet.x, fleet.y), []).append(fleet)

        for (x, y), loc_fleets in locations.items():
            players = {fleet.player_id for fleet in loc_fleets}
            if len(players) < 2:
                continue
            self._resolve_battle_at_location(x, y, loc_fleets)

    def _strongest_player_for_fleets(self, fleets):
        strengths = {}
        for fleet in fleets:
            if fleet.player is None or bool(getattr(fleet.player, 'defeated', False)):
                continue
            strength = calculate_fleet_strength(fleet, 1.0, attack_roll_scale=1.0)
            strengths[fleet.player] = strengths.get(fleet.player, 0.0) + strength
        if not strengths:
            return None
        ranked = sorted(strengths.items(), key=lambda item: item[1], reverse=True)
        if len(ranked) > 1 and abs(ranked[0][1] - ranked[1][1]) < 1e-6:
            return None
        return ranked[0][0]

    def resolve_derelict_encounters(self):
        """Resolve encounters with unowned fleets at shared locations."""
        from .models import Fleet
        derelicts = list(Fleet.objects.filter(game=self.game, player__isnull=True))
        if not derelicts:
            return
        owned_fleets = list(Fleet.objects.filter(
            game=self.game, player__isnull=False, player__defeated=False
        ))
        if not owned_fleets:
            return
        owned_by_location = {}
        for fleet in owned_fleets:
            owned_by_location.setdefault((fleet.x, fleet.y), []).append(fleet)
        for derelict in derelicts:
            candidates = owned_by_location.get((derelict.x, derelict.y))
            if not candidates:
                continue
            winner = self._strongest_player_for_fleets(candidates)
            if winner is None:
                continue
            if roll_chance(DERELICT_CLAIM_CHANCE):
                self._capture_fleet(derelict, winner)
            else:
                self._destroy_derelict_fleet(derelict)

    def first_contact_checks(self):
        """Send first-contact messages for unresolved encounters before combat."""
        from .models import Fleet, Star

        fleets = list(Fleet.objects.filter(game=self.game))

        for fleet in fleets:
            if fleet.player is None or bool(getattr(fleet.player, 'defeated', False)):
                continue
            player = fleet.player
            x, y = fleet.x, fleet.y

            # Star contact
            for star in Star.objects.filter(game=self.game, x=x, y=y).exclude(player=player).exclude(player__isnull=True):
                self._send_first_contact_message(
                    player,
                    'star',
                    star,
                    source_fleet=fleet,
                )

            # Fleet contact
            for other in Fleet.objects.filter(game=self.game, x=x, y=y).exclude(player=player).exclude(player__isnull=True):
                self._send_first_contact_message(
                    player,
                    'fleet',
                    other,
                    source_fleet=fleet,
                )

    def _player_has_other_contacts(self, player):
        """Return True if player has resolved any other player's ownership before."""
        from .models import Player

        for other_player in Player.objects.filter(game=self.game).exclude(id=player.id):
            if self._player_has_contact_with_race(player, other_player):
                return True
        return False

    def _report_reveals_owner(self, report):
        """Return True when a cached report resolves object ownership."""
        if not report:
            return False
        try:
            data = report.get_report_data()
        except Exception:
            return False
        return bool(data.get('player_name'))

    def _player_has_contact_with_race(
        self,
        player,
        other_player,
        exclude_target=None,
    ):
        """Return True if player has already resolved ownership for other_player."""
        from .models import Fleet, PlayerDiplomaticStance, Report, Star

        if not player or not other_player or player.id == other_player.id:
            return False

        if PlayerDiplomaticStance.objects.filter(
            player=player,
            target_player=other_player,
        ).exists():
            return True

        exclude_target = exclude_target or (None, None)
        reports = Report.objects.filter(
            player=player,
            target_type__in=['fleet', 'star'],
        ).order_by('id')

        star_ids = set(
            Star.objects.filter(game=self.game, player=other_player)
            .values_list('id', flat=True)
        )
        fleet_ids = set(
            Fleet.objects.filter(game=self.game, player=other_player)
            .values_list('id', flat=True)
        )

        for report in reports:
            if (report.target_type, report.target_id) == exclude_target:
                continue
            if report.target_type == 'star' and report.target_id not in star_ids:
                continue
            if report.target_type == 'fleet' and report.target_id not in fleet_ids:
                continue
            if self._report_reveals_owner(report):
                return True
        return False

    def _send_first_contact_message(
        self,
        player,
        target_type,
        obj,
        source_fleet=None,
        exclude_target=None,
    ):
        """Send a first-contact message once when another player's identity resolves."""
        from .messages import FirstContactFleetMessageFactory, FirstContactStarMessageFactory

        if not player or not obj:
            return False
        other_player = getattr(obj, 'player', None)
        if other_player is None or other_player == player:
            return False
        if bool(getattr(other_player, 'defeated', False)):
            return False

        pair_key = (player.id, other_player.id)
        if pair_key in self._first_contact_sent:
            return False
        if self._player_has_contact_with_race(
            player,
            other_player,
            exclude_target=exclude_target,
        ):
            self._first_contact_sent.add(pair_key)
            return False

        first_any = (
            player.id not in self._first_contact_any_sent and
            not self._player_has_other_contacts(player)
        )
        if target_type == 'star':
            factory = FirstContactStarMessageFactory(
                self.game, player, source_fleet, obj, first_any=first_any
            )
        elif target_type == 'fleet':
            factory = FirstContactFleetMessageFactory(
                self.game, player, source_fleet, obj, first_any=first_any
            )
        else:
            return False
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()
        ensure_contact_stance_entry(player, other_player)
        self._first_contact_sent.add(pair_key)
        if first_any:
            self._first_contact_any_sent.add(player.id)
        return True

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

        combatant_players = self._combatants_for_location(players)
        if len(combatant_players) < 2:
            return
        fleets_by_player = {
            player: fleets_by_player[player]
            for player in combatant_players
        }
        players = sorted(fleets_by_player.keys(), key=lambda p: p.id)

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
                diplomacy_attack_scale = sum(
                    self._combat_readiness_multiplier(player, f.player) *
                    max(1, f.ship_count)
                    for f in opponent_fleets
                ) / float(total_enemy_ships)
            else:
                opponent_defence = 1.0
                diplomacy_attack_scale = 1.0
            strength_by_player[player] = sum(
                calculate_fleet_strength(
                    fleet,
                    opponent_defence,
                    attack_roll_scale=(
                        roll_attack_scale(
                        getattr(fleet.player.race_type, 'luck_multiplier', 1.0)
                        ) * diplomacy_attack_scale
                    ),
                    offense_bonus_multiplier=self._fleet_ambush_attack_multiplier(fleet),
                )
                for fleet in fleets_by_player[player]
            )

        winner = self._choose_combat_winner(players, strength_by_player)
        damage_taken = self._calculate_combat_damage(strength_by_player)
        results = self._apply_combat_damage(fleets_by_player, damage_taken)
        self._create_combat_encounter_reports(x, y)

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

    def _stance_map_for_player(self, player):
        if not player:
            return {}
        if player.id not in self._stance_map_by_player_id:
            self._stance_map_by_player_id[player.id] = build_stance_map(player)
        return self._stance_map_by_player_id[player.id]

    def _players_should_engage(self, player_a, player_b):
        if not player_a or not player_b or player_a.id == player_b.id:
            return False
        stance_a = stance_towards(
            player_a,
            player_b,
            stance_map=self._stance_map_for_player(player_a),
        )
        stance_b = stance_towards(
            player_b,
            player_a,
            stance_map=self._stance_map_for_player(player_b),
        )
        chance = combat_chance_with_diplomacy_percent(
            stance_a,
            stance_b,
            player_a,
            player_b,
        )
        if chance >= 100:
            return True
        if chance <= 0:
            return False
        return (random.random() * 100.0) < float(chance)

    def _combat_readiness_multiplier(self, player_a, player_b):
        if not player_a or not player_b or player_a.id == player_b.id:
            return 1.0
        stance_a = stance_towards(
            player_a,
            player_b,
            stance_map=self._stance_map_for_player(player_a),
        )
        stance_b = stance_towards(
            player_b,
            player_a,
            stance_map=self._stance_map_for_player(player_b),
        )
        return combat_readiness_multiplier(stance_a, stance_b)

    def _players_can_target_each_other(self, player_a, player_b):
        if not player_a or not player_b or player_a.id == player_b.id:
            return False
        stance_a = stance_towards(
            player_a,
            player_b,
            stance_map=self._stance_map_for_player(player_a),
        )
        stance_b = stance_towards(
            player_b,
            player_a,
            stance_map=self._stance_map_for_player(player_b),
        )
        return combat_chance_with_diplomacy_percent(
            stance_a,
            stance_b,
            player_a,
            player_b,
        ) > 0

    def _combatants_for_location(self, players):
        combatants = set()
        players = [player for player in players if player is not None]
        for idx, player_a in enumerate(players):
            for player_b in players[idx + 1:]:
                if self._players_should_engage(player_a, player_b):
                    combatants.add(player_a)
                    combatants.add(player_b)
        return combatants

    def _create_combat_encounter_reports(self, x, y):
        """Ensure surviving fleets get encounter reports on opposing fleets."""
        from .models import Fleet

        surviving = list(Fleet.objects.filter(
            game=self.game, x=x, y=y, player__isnull=False, player__defeated=False
        ))
        if len(surviving) < 2:
            return
        for fleet in surviving:
            include_cargo = self._player_has_advanced_scanner_at(fleet.player, x, y)
            for other in surviving:
                if other.player_id == fleet.player_id:
                    continue
                self._create_or_update_report(
                    fleet.player,
                    'fleet',
                    other,
                    self.game.year,
                    report_tier='encounter',
                    include_cargo=include_cargo,
                )

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
        salvage_res_x = int(fleet.resource_x_inventory * damage_fraction * COMBAT_SALVAGE_DAMAGE_FACTOR)
        salvage_res_y = int(fleet.resource_y_inventory * damage_fraction * COMBAT_SALVAGE_DAMAGE_FACTOR)
        salvage_res_z = int(fleet.resource_z_inventory * damage_fraction * COMBAT_SALVAGE_DAMAGE_FACTOR)

        if (salvage_dry_mass == 0 and salvage_iron == 0 and salvage_bor == 0 and
                salvage_germ == 0 and salvage_res_x == 0 and salvage_res_y == 0 and salvage_res_z == 0):
            return False

        iron, bor, germ, res_x, res_y, res_z = calculate_salvage_minerals(
            salvage_dry_mass, salvage_iron, salvage_bor, salvage_germ,
            salvage_res_x, salvage_res_y, salvage_res_z,
        )
        if iron == 0 and bor == 0 and germ == 0 and res_x == 0 and res_y == 0 and res_z == 0:
            return False

        self._create_salvage_at_location(
            fleet.x, fleet.y, iron, bor, germ, res_x, res_y, res_z,
            danger_level=self._raw_salvage_danger_level(fleet.x, fleet.y, combat=True),
        )
        return True

    @staticmethod
    def _danger_rank(level):
        order = {
            DANGER_NONE: 0,
            DANGER_LOW: 1,
            DANGER_MEDIUM: 2,
            DANGER_HIGH: 3,
        }
        return order.get(str(level or '').upper(), -1)

    def _raw_salvage_danger_level(self, x, y, combat=False):
        if not combat:
            return DANGER_NONE
        seed = 'raw-salvage:%s:%s:%s' % (self.game.id, int(x), int(y))
        return _pick_level(seed, [DANGER_NONE, DANGER_LOW])

    def _create_salvage_at_location(
        self, x, y, iron, bor, germ, res_x=0, res_y=0, res_z=0, danger_level=None
    ):
        """Create salvage at location, or deposit on star if present."""
        from .models import Star, Salvage
        if iron == 0 and bor == 0 and germ == 0 and res_x == 0 and res_y == 0 and res_z == 0:
            return None

        star = Star.objects.filter(game=self.game, x=x, y=y).first()
        if star:
            star.ironium_inventory += iron
            star.boranium_inventory += bor
            star.germanium_inventory += germ
            star.resource_x_inventory += res_x
            star.resource_y_inventory += res_y
            star.resource_z_inventory += res_z
            star.save()
            self._discover_secret_resources_from_star(star.player, star)
            return star

        salvage, created = Salvage.objects.get_or_create(
            game=self.game, x=x, y=y,
            defaults={
                'danger_level': str(danger_level or ''),
                'ironium_inventory': iron,
                'boranium_inventory': bor,
                'germanium_inventory': germ,
                'resource_x_inventory': res_x,
                'resource_y_inventory': res_y,
                'resource_z_inventory': res_z,
            }
        )
        if not created:
            salvage.ironium_inventory += iron
            salvage.boranium_inventory += bor
            salvage.germanium_inventory += germ
            salvage.resource_x_inventory += res_x
            salvage.resource_y_inventory += res_y
            salvage.resource_z_inventory += res_z
            update_fields = [
                'ironium_inventory', 'boranium_inventory', 'germanium_inventory',
                'resource_x_inventory', 'resource_y_inventory', 'resource_z_inventory',
            ]
            if danger_level is not None:
                existing_rank = self._danger_rank(getattr(salvage, 'danger_level', ''))
                incoming_rank = self._danger_rank(danger_level)
                if incoming_rank > existing_rank:
                    salvage.danger_level = str(danger_level or '')
                    update_fields.append('danger_level')
            salvage.save(update_fields=update_fields)
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
                elif transfer_result == 'fleet_destroyed':
                    return None
                elif transfer_result == 'waiting':
                    # Transfer blocked - stop processing
                    break

            elif order.order_type == 'REFUEL':
                refuel_result = self._execute_refuel_order(fleet, order)
                if refuel_result == 'executed':
                    self._handle_repeating_order(order)
                    order.delete()
                    continue
                elif refuel_result == 'waiting':
                    break

            elif order.order_type in ['MOVE', 'INTERCEPT']:
                self._handle_hidden_fleet_target(fleet, order)
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

            elif order.order_type == 'GIVE':
                give_result = self._execute_give_order(fleet, order)
                if give_result == 'executed':
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
        is_intercept = order.order_type == 'INTERCEPT'
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

        def _heading_for_vector(vec):
            """Return heading for vector where 0=north, 90=east."""
            dx, dy = vec[0], vec[1]
            return degrees(atan2(dx, -dy)) % 360

        heading_to_target = _heading_for_vector(vector) if distance > 0 else None

        # Check if fleet can reach destination this turn
        warp_speed = order.warpfactor if order.order_type in ['MOVE', 'INTERCEPT'] else 5
        if is_intercept and warp_speed == WORMHOLE_WARPFACTOR:
            warp_speed = 13
            if int(order.warpfactor or 0) == WORMHOLE_WARPFACTOR:
                order.warpfactor = 13
                order.save(update_fields=['warpfactor'])
        if distance > 0:
            if warp_speed == WORMHOLE_WARPFACTOR and bool(fleet.has_wormhole_drive):
                if not self._consume_wormhole_jump_fuel(fleet, distance):
                    self._create_wormhole_fuel_failure_message(
                        fleet,
                        self._wormhole_jump_fuel_cost(fleet, distance),
                    )
                    return False
            else:
                if warp_speed == WORMHOLE_WARPFACTOR:
                    warp_speed = 13
                warp_speed = self._resolve_movement_warp_with_fuel(fleet, order, warp_speed)
                if warp_speed <= 0:
                    return False

        # If target fleet is already within intercept range, snap directly to it.
        # This avoids "parking ahead" when predictive lead is unnecessary.
        if is_intercept:
            target_obj, target_x, target_y, _target_kind = self._get_live_intercept_target(order)
            if target_x is None or target_y is None:
                target_obj = None
            target_position = (
                nparray([target_x, target_y]) if target_obj is not None else None
            )
        else:
            target_obj = None
            target_position = None

        if is_intercept:
            effective_warp_speed = self._raw_movement_speed(warp_speed)
        else:
            effective_warp_speed = self._effective_movement_speed(
                fleet, warp_speed
            )

        if is_intercept and target_position is not None:
            live_distance = linalg.norm(
                target_position - position
            )
            if self._is_within_intercept_snap_range(live_distance, effective_warp_speed):
                live_vector = target_position - position
                if linalg.norm(live_vector) > 0:
                    fleet.heading = _heading_for_vector(live_vector)
                    fleet.travel_warp = max(0, int(warp_speed))
                else:
                    fleet.travel_warp = 0
                fleet.x = int(target_x)
                fleet.y = int(target_y)
                return True

        if warp_speed == WORMHOLE_WARPFACTOR and bool(fleet.has_wormhole_drive):
            if heading_to_target is not None:
                fleet.heading = heading_to_target
                fleet.travel_warp = max(0, int(warp_speed))
            else:
                fleet.travel_warp = 0
            jump_result = self._execute_wormhole_jump(fleet, order, x, y, distance)
            if jump_result == 'destroyed':
                return 'destroyed'
            if jump_result == 'arrived':
                if is_intercept:
                    return self._intercept_target_matched(order, fleet)
                return True
            return False

        # Check for warp damage before moving
        damage_result = self._check_warp_damage(fleet, warp_speed, order)
        if damage_result == 'destroyed':
            return 'destroyed'

        if int(distance) <= effective_warp_speed:
            # Fleet reaches destination
            if heading_to_target is not None:
                fleet.heading = heading_to_target
                fleet.travel_warp = max(0, int(warp_speed))
            else:
                fleet.travel_warp = 0
            fleet.x = x
            fleet.y = y
            if is_intercept:
                return self._intercept_target_matched(order, fleet)
            return True
        else:
            # Fleet moves toward destination but doesn't reach it
            normalised_vector = vector / distance
            step_vector = normalised_vector * effective_warp_speed
            seed_key = str(getattr(fleet, 'short_id', None) or getattr(fleet, 'id', ''))
            step_x = self._quantized_axis_step(step_vector[0], seed_key, 'x')
            step_y = self._quantized_axis_step(step_vector[1], seed_key, 'y')
            new_x = fleet.x + step_x
            new_y = fleet.y + step_y
            # Ensure progress even with low warp + diagonal movement
            if new_x == fleet.x and new_y == fleet.y:
                step_x = 0 if vector[0] == 0 else (1 if vector[0] > 0 else -1)
                step_y = 0 if vector[1] == 0 else (1 if vector[1] > 0 else -1)
                new_x = fleet.x + step_x
                new_y = fleet.y + step_y
            if heading_to_target is not None:
                fleet.heading = heading_to_target
                fleet.travel_warp = max(0, int(warp_speed))
            else:
                fleet.travel_warp = 0
            fleet.x = new_x
            fleet.y = new_y
            if (fleet.x, fleet.y) == (x, y):
                if is_intercept:
                    return self._intercept_target_matched(order, fleet)
                return True
            if is_intercept:
                if self._intercept_target_matched(order, fleet):
                    return True
            return False

    def _execute_wormhole_jump(self, fleet, order, target_x, target_y, distance):
        """Resolve one wormhole jump attempt.

        Returns:
        - 'destroyed': fleet destroyed during jump
        - 'arrived': fleet reached intended target
        - 'deviated': fleet arrived off-target due to deviation
        """
        start_x = int(fleet.x)
        start_y = int(fleet.y)
        target_x = int(target_x)
        target_y = int(target_y)

        try:
            destruction_chance = float(getattr(fleet, 'wormhole_destruction_chance', None))
        except (TypeError, ValueError):
            destruction_chance = None
        if destruction_chance is None:
            destruction_chance = WORMHOLE_DESTRUCTION_CHANCE
        destruction_chance = max(0.0, min(1.0, destruction_chance))
        if roll_chance(destruction_chance):
            self._handle_wormhole_destruction(
                fleet,
                from_damage=False,
                start_x=start_x,
                start_y=start_y,
                destination_x=target_x,
                destination_y=target_y,
            )
            return 'destroyed'

        max_integrity_damage = int(
            float(distance) / 100.0 * float(WORMHOLE_MAX_INTEGRITY_DAMAGE_PER_100_LY)
        )
        if max_integrity_damage > 0 and roll_chance(WORMHOLE_INTEGRITY_DAMAGE_CHANCE):
            integrity_loss = random.randint(1, max_integrity_damage)
            integrity_loss = min(integrity_loss, int(fleet.integrity or 0))
            if integrity_loss > 0:
                fleet.integrity -= integrity_loss
                if fleet.integrity <= 0:
                    self._handle_wormhole_destruction(
                        fleet,
                        from_damage=True,
                        start_x=start_x,
                        start_y=start_y,
                        destination_x=target_x,
                        destination_y=target_y,
                    )
                    return 'destroyed'
                self._create_warp_damage_message(
                    fleet, WORMHOLE_WARPFACTOR, integrity_loss, {}, 0
                )

        arrived_exactly = roll_chance(WORMHOLE_ARRIVAL_CHANCE)

        destination_x = int(target_x)
        destination_y = int(target_y)
        deviated = False
        can_deviate = distance >= WORMHOLE_DEVIATION_MIN_DISTANCE
        if can_deviate and (not arrived_exactly) and roll_chance(WORMHOLE_DEVIATION_CHANCE):
            max_deviation = int(
                round((float(distance) / 50.0) * WORMHOLE_DEVIATION_LY_PER_50)
            )
            max_deviation = max(1, max_deviation)
            theta = random.uniform(0.0, 2.0 * pi)
            radius = random.uniform(0.0, float(max_deviation))
            dx = int(round(cos(theta) * radius))
            dy = int(round(sin(theta) * radius))
            destination_x += dx
            destination_y += dy
            deviated = True

        destination_x = max(0, min(int(self.game.map_size_x), destination_x))
        destination_y = max(0, min(int(self.game.map_size_y), destination_y))
        fleet.x = destination_x
        fleet.y = destination_y
        self._create_wormhole_jump_success_message(
            fleet,
            destination_x,
            destination_y,
        )
        if deviated and (destination_x, destination_y) != (int(target_x), int(target_y)):
            return 'deviated'
        return 'arrived'

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
        # Baseline curve: low warp is cheap, safe warp is around 3.0mg per ship-year.
        cruise_cost = 0.15 + 1.35 * (cruise_normalised ** 1.4)

        overmax_cost = 0.0
        if normalised > 1.0:
            over = normalised - 1.0
            # Exponential overmax burn; propulsion tech can worsen/improve this.
            overmax_cost = overmax_penalty * 0.6 * ((2.0 ** (over * 1.6)) - 1.0)

        per_ship_cost = max(0.05, (cruise_cost + overmax_cost) / fuel_efficiency)
        per_ship_cost *= FUEL_CONSUMPTION_MULTIPLIER
        return per_ship_cost * ship_count

    def _wormhole_jump_fuel_cost(self, fleet, distance):
        """Fuel required for one wormhole jump based on distance."""
        distance = max(0.0, float(distance or 0.0))
        if distance <= 0.0:
            return 0.0
        per_ly = max(0.1, float(getattr(fleet, 'wormhole_fuel_per_ly', 5.0) or 5.0))
        return per_ly * distance

    def _consume_wormhole_jump_fuel(self, fleet, distance):
        """Consume fuel for a wormhole jump; return False when fuel is insufficient."""
        cost = self._wormhole_jump_fuel_cost(fleet, distance)
        if float(fleet.fuel) < cost:
            return False
        fleet.fuel = max(0.0, float(fleet.fuel) - cost)
        return True

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

    def _create_wormhole_fuel_failure_message(self, fleet, required_fuel):
        if fleet.player is None:
            return
        factory = FleetWormholeFuelFailureMessageFactory(
            self.game,
            fleet.player,
            fleet,
            getattr(fleet, 'fuel', 0.0),
            required_fuel,
        )
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def _create_wormhole_jump_success_message(self, fleet, destination_x, destination_y):
        if fleet.player is None:
            return
        factory = FleetWormholeJumpSuccessMessageFactory(
            self.game,
            fleet.player,
            fleet,
            destination_x,
            destination_y,
        )
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

    def _fleet_has_active_fuel_factory(self, fleet, warp_speed):
        try:
            fuel_factory_rate = float(
                getattr(fleet, 'fuel_factory_mg_per_year', 0.0) or 0.0
            )
        except (TypeError, ValueError):
            fuel_factory_rate = 0.0
        if fuel_factory_rate <= 0.0:
            return False
        try:
            fuel_factory_max_warp = int(
                getattr(fleet, 'fuel_factory_max_warp', -1)
            )
        except (TypeError, ValueError):
            fuel_factory_max_warp = -1
        try:
            warp_speed = int(warp_speed)
        except (TypeError, ValueError):
            warp_speed = -1
        return fuel_factory_max_warp >= 0 and warp_speed <= fuel_factory_max_warp

    def apply_fuel_factories(self):
        """Apply yearly fuel-factory output after movement and combat."""
        for fleet in self.game.fleets.filter(
            player__isnull=False,
            player__defeated=False,
        ):
            if not self._fleet_has_active_fuel_factory(
                fleet,
                getattr(fleet, 'travel_warp', 0),
            ):
                continue
            try:
                fuel_factory_rate = float(
                    getattr(fleet, 'fuel_factory_mg_per_year', 0.0) or 0.0
                )
            except (TypeError, ValueError):
                fuel_factory_rate = 0.0
            if fuel_factory_rate <= 0.0:
                continue
            old_fuel = float(getattr(fleet, 'fuel', 0.0) or 0.0)
            max_fuel = float(getattr(fleet, 'max_fuel', 0.0) or 0.0)
            if old_fuel >= max_fuel:
                continue
            fleet.fuel = min(max_fuel, old_fuel + fuel_factory_rate)
            if float(fleet.fuel) != old_fuel:
                fleet.save(update_fields=['fuel'])

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
            # If both started stacked this year, don't immobilize the target,
            # but still treat it as a continuing encounter for ambush tracking.
            self._record_intercept_contact(interceptor, order, allow_ambush=False)
            return

        self._record_intercept_contact(interceptor, order, allow_ambush=True)
        self._locked_fleet_ids_for_year.add(interceptor.id)
        self._locked_fleet_ids_for_year.add(target.id)

    def _record_intercept_contact(self, interceptor, order, allow_ambush=True):
        """Record an intercept encounter and optionally grant a fresh-contact ambush."""
        last_contact_year = getattr(order, 'last_contact_year', None)
        is_fresh_contact = (
            last_contact_year is None or int(self.game.year) > int(last_contact_year) + 1
        )
        if allow_ambush and is_fresh_contact and fleet_is_cloaked(interceptor):
            self._ambush_fleet_ids_for_year.add(interceptor.id)
        order.last_contact_year = int(self.game.year)

    def _mark_cloaked_intercept_ambush(self, interceptor, order):
        """Backward-compatible wrapper for tests and existing callers."""
        self._record_intercept_contact(interceptor, order, allow_ambush=True)

    def _fleet_ambush_attack_multiplier(self, fleet):
        """Return offense bonus multiplier for fleets with a fresh ambush."""
        if getattr(fleet, 'id', None) not in self._ambush_fleet_ids_for_year:
            return 1.0
        return roll_ambush_attack_multiplier(
            getattr(fleet.player.race_type, 'luck_multiplier', 1.0)
        )

    def _get_intercept_destination(self, order):
        """Calculate intercept destination based on moving target prediction."""
        from math import radians, sin, cos

        target_obj, x, y, kind = order.get_actual_target()
        if kind in ['invalid', 'none']:
            return order.fleet.x, order.fleet.y

        if kind == 'anomaly' and target_obj is not None:
            from .models import Anomaly
            if getattr(target_obj, 'anomaly_type', None) == Anomaly.TYPE_COMET:
                return self._predict_comet_intercept_destination(order.fleet, order, target_obj)
            return target_obj.x, target_obj.y

        if not order.target_fleet:
            return x, y

        target_fleet = order.target_fleet
        if not self._fleet_target_visible_to_player(order.fleet.player, target_fleet):
            return order.fleet.x, order.fleet.y
        target_speed = self._get_fleet_current_speed(
            target_fleet,
            ignore_movement_modifiers=True,
        )
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

    def _predict_comet_position(self, comet, years_ahead):
        """Project comet position assuming heading continues as-is."""
        from math import radians, sin, cos
        years = max(0, int(years_ahead or 0))
        x = int(comet.x)
        y = int(comet.y)
        heading = self._normalize_heading(getattr(comet, 'heading', 0.0))
        theta = radians(heading)
        dx = sin(theta) * ANOMALY_COMET_DRIFT_WARP
        dy = -cos(theta) * ANOMALY_COMET_DRIFT_WARP
        max_x = max(1, int(self.game.map_size_x) - 1)
        max_y = max(1, int(self.game.map_size_y) - 1)
        for year_offset in range(years):
            step_x = self._quantized_axis_step(dx, comet.short_id, 'x', year=self.game.year + year_offset)
            step_y = self._quantized_axis_step(dy, comet.short_id, 'y', year=self.game.year + year_offset)
            next_x = x + step_x
            next_y = y + step_y
            if next_x < 1 or next_x > max_x or next_y < 1 or next_y > max_y:
                # Comet is expected to collapse out of map bounds; intercept best-known position.
                return x, y
            x = int(next_x)
            y = int(next_y)
        return x, y

    def _predict_comet_intercept_destination(self, interceptor, order, comet):
        """Lead comet intercept point based on interceptor speed and comet heading."""
        warp_speed = max(1, int(getattr(order, 'warpfactor', 1) or 1))
        intercept_speed = max(1.0, float(self._raw_movement_speed(warp_speed)))
        ix, iy = int(interceptor.x), int(interceptor.y)
        px, py = int(comet.x), int(comet.y)
        for _ in range(4):
            distance = linalg.norm(nparray([px, py]) - nparray([ix, iy]))
            years = max(0, int(ceil(distance / intercept_speed)))
            projected_x, projected_y = self._predict_comet_position(comet, years)
            if (projected_x, projected_y) == (px, py):
                break
            px, py = projected_x, projected_y
        return int(px), int(py)

    def _get_live_intercept_target(self, order):
        """Return current live target tuple for intercept checks."""
        if order.target_fleet:
            target = order.target_fleet
            return target, target.x, target.y, 'fleet'
        obj, x, y, kind = order.get_actual_target()
        return obj, x, y, kind

    def _intercept_target_matched(self, order, fleet):
        """Return True when interceptor is co-located with current target location."""
        _obj, tx, ty, _kind = self._get_live_intercept_target(order)
        if tx is None or ty is None:
            return False
        return (int(fleet.x), int(fleet.y)) == (int(tx), int(ty))

    def _is_interceptor_ahead_of_target(self, interceptor, target_fleet):
        """Return True when interceptor is ahead along target's movement vector."""
        from math import radians, sin, cos

        target_speed = self._get_fleet_current_speed(
            target_fleet,
            ignore_movement_modifiers=True,
        )
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
        try:
            speed = float(warp_speed or 0.0)
        except (TypeError, ValueError):
            speed = 0.0
        if speed <= 0:
            return False
        return max(0.0, float(distance) - 0.35) <= speed

    def _get_warp_speed_multiplier(self):
        try:
            value = float(getattr(self.game, 'warp_speed_multiplier', 1.0) or 1.0)
        except (TypeError, ValueError):
            value = 1.0
        return max(0.1, value)

    def _fleet_warp_advantage(self, fleet, base_warp=0):
        """Return additive warp advantage for standard movement speeds."""
        try:
            base = int(base_warp or 0)
        except (TypeError, ValueError):
            base = 0
        if base <= 0 or base == WORMHOLE_WARPFACTOR:
            return 0.0
        try:
            return float(getattr(fleet, 'warp_advantage', 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _effective_movement_speed(self, fleet, warp_speed):
        """Return effective yearly movement speed after global and fleet modifiers."""
        speed_multiplier = self._get_warp_speed_multiplier()
        base_speed = max(0.0, float(warp_speed or 0.0) * speed_multiplier)
        if int(warp_speed or 0) == WORMHOLE_WARPFACTOR:
            return base_speed
        return max(0.0, base_speed + self._fleet_warp_advantage(fleet, warp_speed))

    def _raw_movement_speed(self, warp_speed):
        """Return unmodified yearly movement speed from the selected warp only."""
        return max(0.0, float(warp_speed or 0.0))

    def _get_fleet_current_speed(self, fleet, ignore_movement_modifiers=False):
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
            warp_speed = max(0, int(order.warpfactor or 0))
            if warp_speed == WORMHOLE_WARPFACTOR and bool(getattr(fleet, 'has_wormhole_drive', False)):
                return warp_speed
            if ignore_movement_modifiers:
                return self._raw_movement_speed(warp_speed)
            return self._effective_movement_speed(fleet, warp_speed)
        return 0

    def _check_warp_damage(self, fleet, warp_speed, order):
        """Check if fleet takes damage from exceeding safe warp speed.

        Returns: 'destroyed', 'damaged', or 'safe'
        """
        if bool(getattr(order, 'overmax_risk_checked', False)):
            return 'safe'
        if warp_speed <= fleet.max_safe_warp:
            return 'safe'

        order.overmax_risk_checked = True
        order.save(update_fields=['overmax_risk_checked'])

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

    def _get_requested_order_warpfactor(self, order):
        warp = getattr(order, 'original_warpfactor', None)
        if warp is None:
            warp = order.warpfactor
        return max(0, int(warp or 0))

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

        if fleet.resource_x_inventory > 0:
            loss = int(fleet.resource_x_inventory * cargo_loss_percent)
            if loss > 0:
                cargo_losses['resource_x'] = loss
                fleet.resource_x_inventory -= loss

        if fleet.resource_y_inventory > 0:
            loss = int(fleet.resource_y_inventory * cargo_loss_percent)
            if loss > 0:
                cargo_losses['resource_y'] = loss
                fleet.resource_y_inventory -= loss

        if fleet.resource_z_inventory > 0:
            loss = int(fleet.resource_z_inventory * cargo_loss_percent)
            if loss > 0:
                cargo_losses['resource_z'] = loss
                fleet.resource_z_inventory -= loss

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

        if fleet.player is not None:
            factory = FleetWarpDestroyedMessageFactory(
                self.game, fleet.player, fleet.name, warp_speed,
                fleet.x, fleet.y, from_damage, salvage_created, salvage_location
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()
        fleet.delete()

    def _handle_wormhole_destruction(
        self, fleet, from_damage=False, start_x=None, start_y=None,
        destination_x=None, destination_y=None,
    ):
        """Destroy fleet during wormhole transit and send wormhole-specific message."""
        salvage_created = False
        salvage_location = None

        if roll_chance(SALVAGE_CHANCE_WARP):
            salvage_result = self._create_salvage_from_fleet(fleet)
            if salvage_result:
                salvage_created = True
                salvage_location = salvage_result

        if fleet.player is not None:
            factory = FleetWormholeDestroyedMessageFactory(
                self.game,
                fleet.player,
                fleet.name,
                fleet.x,
                fleet.y,
                from_damage,
                salvage_created,
                salvage_location,
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()
        self._maybe_spawn_wormhole_drive_anomaly(start_x, start_y, destination_x, destination_y)
        fleet.delete()

    def _maybe_spawn_wormhole_drive_anomaly(self, start_x, start_y, destination_x, destination_y):
        """Rarely spawn a rift/black hole/wormhole near wormhole loss start/destination."""
        if not bool(getattr(self.game, 'anomalies_enabled', False)):
            return
        total_chance = (
            WORMHOLE_DRIVE_RIFT_CHANCE
            + WORMHOLE_DRIVE_BLACK_HOLE_CHANCE
            + WORMHOLE_DRIVE_WORMHOLE_CHANCE
        )
        roll = random.random()
        if roll >= total_chance:
            return

        try:
            sx = int(start_x)
            sy = int(start_y)
            dx = int(destination_x)
            dy = int(destination_y)
        except (TypeError, ValueError):
            return

        from .models import Anomaly, Star, Fleet, Salvage

        max_x = max(1, int(self.game.map_size_x) - 1)
        max_y = max(1, int(self.game.map_size_y) - 1)
        star_positions = set(Star.objects.filter(game=self.game).values_list('x', 'y'))
        occupied = set(Fleet.objects.filter(game=self.game).values_list('x', 'y'))
        occupied.update(Salvage.objects.filter(game=self.game).values_list('x', 'y'))
        occupied.update(Anomaly.objects.filter(game=self.game).values_list('x', 'y'))

        offsets = []
        max_d = int(WORMHOLE_RIFT_MAX_DISTANCE)
        for ox in range(-max_d, max_d + 1):
            for oy in range(-max_d, max_d + 1):
                dist = ((ox * ox) + (oy * oy)) ** 0.5
                if WORMHOLE_RIFT_MIN_DISTANCE <= dist <= WORMHOLE_RIFT_MAX_DISTANCE:
                    offsets.append((ox, oy))
        random.shuffle(offsets)

        anchors = [(sx, sy), (dx, dy)]
        if random.random() < 0.5:
            anchors.reverse()

        def find_spawn_near(anchor_x, anchor_y, blocked):
            for ox, oy in offsets:
                x = int(anchor_x + ox)
                y = int(anchor_y + oy)
                if x < 1 or x > max_x or y < 1 or y > max_y:
                    continue
                key = (x, y)
                if key in star_positions or key in blocked:
                    continue
                return x, y
            return None, None

        if roll < WORMHOLE_DRIVE_RIFT_CHANCE:
            anomaly_type = Anomaly.TYPE_RIFT
        elif roll < (WORMHOLE_DRIVE_RIFT_CHANCE + WORMHOLE_DRIVE_BLACK_HOLE_CHANCE):
            anomaly_type = Anomaly.TYPE_BLACK_HOLE
        else:
            anomaly_type = Anomaly.TYPE_WORMHOLE

        if anomaly_type == Anomaly.TYPE_WORMHOLE:
            start_x, start_y = find_spawn_near(sx, sy, occupied)
            if start_x is None:
                return
            occupied.add((start_x, start_y))
            dest_x, dest_y = find_spawn_near(dx, dy, occupied)
            if dest_x is None:
                return
            base_index = Anomaly.objects.filter(game=self.game).count() + 1
            name_a = 'Wormhole %s' % base_index
            name_b = 'Wormhole %s' % (base_index + 1)
            a = Anomaly.objects.create(
                game=self.game,
                x=start_x,
                y=start_y,
                anomaly_type=Anomaly.TYPE_WORMHOLE,
                name=name_a,
                heading=random.random() * 360.0,
                stability=random.randint(
                    WORMHOLE_DRIVE_WORMHOLE_STABILITY_MIN,
                    WORMHOLE_DRIVE_WORMHOLE_STABILITY_MAX,
                ),
            )
            b = Anomaly.objects.create(
                game=self.game,
                x=dest_x,
                y=dest_y,
                anomaly_type=Anomaly.TYPE_WORMHOLE,
                name=name_b,
                heading=random.random() * 360.0,
                stability=random.randint(
                    WORMHOLE_DRIVE_WORMHOLE_STABILITY_MIN,
                    WORMHOLE_DRIVE_WORMHOLE_STABILITY_MAX,
                ),
                wormhole_pair=a,
            )
            a.wormhole_pair = b
            a.save(update_fields=['wormhole_pair'])
            return

        for ax, ay in anchors:
            x, y = find_spawn_near(ax, ay, occupied)
            if x is None:
                continue
            label = 'Rift' if anomaly_type == Anomaly.TYPE_RIFT else 'Black Hole'
            Anomaly.objects.create(
                game=self.game,
                x=x,
                y=y,
                anomaly_type=anomaly_type,
                name='%s %s' % (label, Anomaly.objects.filter(game=self.game).count() + 1),
                heading=random.random() * 360.0,
                stability=random.randint(30, 91),
            )
            return

    def _create_salvage_from_fleet(self, fleet):
        """Create salvage from fleet destruction or scuttling.

        If at a star location, deposits minerals on star surface instead.
        Returns the salvage/star object created/updated, or None if no minerals.
        """
        from .models import Star, Salvage

        iron, bor, germ, res_x, res_y, res_z = calculate_salvage_minerals(
            fleet.dry_mass,
            fleet.ironium_inventory,
            fleet.boranium_inventory,
            fleet.germanium_inventory,
            fleet.resource_x_inventory,
            fleet.resource_y_inventory,
            fleet.resource_z_inventory,
        )

        # If no minerals, no salvage created
        if iron == 0 and bor == 0 and germ == 0 and res_x == 0 and res_y == 0 and res_z == 0:
            return None

        # Check for star at location - deposit on surface instead
        star = Star.objects.filter(
            game=self.game, x=fleet.x, y=fleet.y
        ).first()

        if star:
            star.ironium_inventory += iron
            star.boranium_inventory += bor
            star.germanium_inventory += germ
            star.resource_x_inventory += res_x
            star.resource_y_inventory += res_y
            star.resource_z_inventory += res_z
            star.save()
            self._discover_secret_resources_from_star(star.player, star)
            return star

        # No star - create or add to existing salvage pile
        return self._create_salvage_at_location(
            fleet.x, fleet.y, iron, bor, germ, res_x, res_y, res_z,
            danger_level=self._raw_salvage_danger_level(fleet.x, fleet.y, combat=True),
        )

    def _abandon_fleet(self, fleet):
        """Mark a fleet as unowned and clear its orders."""
        fleet.orders.all().delete()
        fleet.player = None
        fleet.travel_warp = 0
        fleet.save(update_fields=['player', 'travel_warp'])

    def _capture_fleet(self, fleet, new_owner):
        """Transfer fleet ownership to a new player and clear orders."""
        fleet.orders.all().delete()
        fleet.player = new_owner
        fleet.travel_warp = 0
        fleet.save(update_fields=['player', 'travel_warp'])

    def _destroy_derelict_fleet(self, fleet):
        """Destroy an unowned fleet and create salvage if possible."""
        self._create_salvage_from_fleet(fleet)
        fleet.delete()

    def _create_warp_damage_message(self, fleet, warp_speed, integrity_loss,
                                     cargo_losses, colonist_deaths):
        """Create a message for warp damage."""
        if fleet.player is None:
            return
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
            repeat_warpfactor = self._get_requested_order_warpfactor(order)
            FleetOrders.objects.create(
                game=self.game,
                fleet=order.fleet,
                order_type=order.order_type,
                repeat=True,
                warpfactor=repeat_warpfactor,
                original_warpfactor=repeat_warpfactor,
                overmax_risk_checked=False,
                x=order.x,
                y=order.y,
                target_kind=order.target_kind,
                target_short_id=order.target_short_id,
                target_star_id=order.target_star_id,
                target_fleet_id=order.target_fleet_id,
                target_salvage_id=order.target_salvage_id,
                transfer_type=order.transfer_type,
                transfer_ironium=order.transfer_ironium,
                transfer_boranium=order.transfer_boranium,
                transfer_germanium=order.transfer_germanium,
                transfer_resource_x=order.transfer_resource_x,
                transfer_resource_y=order.transfer_resource_y,
                transfer_resource_z=order.transfer_resource_z,
                transfer_colonists=order.transfer_colonists,
                transfer_fuel=order.transfer_fuel,
                transfer_player_id=order.transfer_player_id,
                patrol_radius=order.patrol_radius,
                intercept_speed=order.intercept_speed,
                patrol_generated=order.patrol_generated,
                last_contact_year=order.last_contact_year,
                bomb_until=order.bomb_until,
                mine_until_full=order.mine_until_full,
                added_by_micromanager=bool(
                    getattr(order, 'added_by_micromanager', False)
                ),
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

        if target_kind == 'star' and target_obj is not None:
            # Stars don't move, so always available
            if target_obj.x != target_x or target_obj.y != target_y:
                print(f"Warning: Star {target_obj.name} coordinates mismatch")

        elif target_kind == 'fleet' and target_obj is not None:
            # Check if target fleet is at expected location
            if target_obj.x != target_x or target_obj.y != target_y:
                print(f"Transfer waiting: Fleet {target_obj.name} not at expected location ({target_x}, {target_y})")
                return 'waiting'  # Block and wait for target fleet to arrive

        elif target_kind == 'salvage' and target_obj is not None:
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
            transfer_result = self._transfer_with_star(fleet, order, target_obj)
            if transfer_result == 'fleet_destroyed':
                return 'fleet_destroyed'
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

    def _execute_refuel_order(self, source_fleet, order):
        """Transfer fuel to another same-location fleet."""
        target_fleet = getattr(order, 'target_fleet', None)
        if not target_fleet:
            return 'executed'
        if source_fleet.id == target_fleet.id:
            return 'executed'
        if (int(source_fleet.x), int(source_fleet.y)) != (int(target_fleet.x), int(target_fleet.y)):
            return 'waiting'

        try:
            requested = float(getattr(order, 'transfer_fuel', 0.0) or 0.0)
        except (TypeError, ValueError):
            requested = 0.0
        available = max(0.0, float(getattr(source_fleet, 'fuel', 0.0) or 0.0))
        target_missing = max(
            0.0,
            float(getattr(target_fleet, 'max_fuel', 0.0) or 0.0) -
            float(getattr(target_fleet, 'fuel', 0.0) or 0.0)
        )
        transfer_amount = min(requested, available, target_missing)
        if transfer_amount <= 0.0:
            return 'executed'

        source_fleet.fuel = max(0.0, float(source_fleet.fuel) - transfer_amount)
        target_fleet.fuel = min(
            float(target_fleet.max_fuel or 0.0),
            float(target_fleet.fuel or 0.0) + transfer_amount,
        )
        source_fleet.save(update_fields=['fuel'])
        target_fleet.save(update_fields=['fuel'])
        return 'executed'

    def _transfer_with_space(self, fleet, order, target_x, target_y):
        """Execute transfer to empty space (creates/updates salvage)."""
        if order.transfer_type not in ('UNLOAD', 'UNLOAD_ALL'):
            return

        resource_keys = ALL_RESOURCE_KEYS
        transfers = {}
        if order.transfer_type == 'UNLOAD_ALL':
            for key in resource_keys:
                transfers[key] = int(getattr(fleet, f'{key}_inventory', 0) or 0)
            colonists_transfer = int(fleet.colonists or 0)
        else:
            for key in resource_keys:
                requested = int(getattr(order, f'transfer_{key}', 0) or 0)
                available = int(getattr(fleet, f'{key}_inventory', 0) or 0)
                transfers[key] = min(requested, available)
            colonists_transfer = min(int(order.transfer_colonists or 0), int(fleet.colonists or 0))

        if sum(transfers.values()) == 0 and colonists_transfer == 0:
            return

        for key in resource_keys:
            setattr(
                fleet,
                f'{key}_inventory',
                int(getattr(fleet, f'{key}_inventory', 0) or 0) - transfers[key]
            )
        fleet.colonists -= colonists_transfer
        fleet.save()

        if colonists_transfer > 0:
            factory = ColonistsLostInSpaceMessageFactory(
                self.game, fleet.player, fleet, colonists_transfer, target_x, target_y
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()

        if sum(transfers.values()) > 0:
            self._create_salvage_at_location(
                target_x, target_y,
                transfers.get('ironium', 0),
                transfers.get('boranium', 0),
                transfers.get('germanium', 0),
                transfers.get('resource_x', 0),
                transfers.get('resource_y', 0),
                transfers.get('resource_z', 0),
                danger_level=DANGER_NONE,
            )

    def _handle_invasion(self, fleet, star, invader_colonists_kt):
        """Resolve invasion when colonists are transferred to an enemy colony."""
        from .messages import InvasionReportMessageFactory
        from .models import Fleet

        if invader_colonists_kt <= 0:
            return

        attacker = fleet.player
        defender = star.player
        defender_race = defender.race_type if defender else None
        attacker_race = attacker.race_type
        attacker_readiness = self._combat_readiness_multiplier(attacker, defender)
        defender_readiness = self._combat_readiness_multiplier(defender, attacker)

        fleet_losses_desc = "no fleet losses"
        effective_defenses = calculate_effective_defenses(star)
        if effective_defenses > 0:
            defender_defence_mult = self._get_colony_defense_multiplier(defender, star)
            attacker_strength = calculate_fleet_strength(
                fleet,
                defender_defence_mult,
                attack_roll_scale=attacker_readiness,
            )
            defender_strength = normalize_ship_count(effective_defenses) * defender_readiness
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

        attacker_ground_force_multiplier = (
            attacker_race.ground_force_multiplier
            if attacker_race.ground_force_multiplier is not None
            else 1.0
        )
        defender_ground_force_multiplier = (
            defender_race.ground_force_multiplier
            if defender_race and defender_race.ground_force_multiplier is not None
            else 1.0
        )
        attacker_ground_readiness = sqrt(attacker_readiness)
        defender_ground_readiness = sqrt(defender_readiness)

        attacker_force = (
            invaders *
            attacker_ground_force_multiplier *
            attacker_ground_readiness
        )
        defender_force = (
            defenders *
            defender_ground_force_multiplier *
            defender_ground_readiness
        )

        attacker_won = attacker_force > defender_force
        if attacker_force == defender_force:
            attacker_won = False

        if attacker_won:
            remaining_invaders = int(
                (attacker_force - defender_force) /
                (attacker_ground_force_multiplier * attacker_ground_readiness)
            )
            attacker_losses = invaders - remaining_invaders
            defender_losses = defenders
            star.colonists = max(0, remaining_invaders)
            star.player = attacker
            star.save(update_fields=['colonists', 'player'])
            if defender:
                self._handle_homeworld_loss(
                    defender,
                    lost_star=star,
                    location=(star.x, star.y),
                )
        else:
            if defender_ground_force_multiplier > 0 and defender_ground_readiness > 0:
                remaining_defenders = int(
                    (defender_force - attacker_force) /
                    (defender_ground_force_multiplier * defender_ground_readiness)
                )
            else:
                remaining_defenders = 0
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

        # Surviving invasion fleets grant encounter-grade reports to both sides.
        if Fleet.objects.filter(id=fleet.id).exists():
            self._create_or_update_report(
                attacker, 'star', star, self.game.year, report_tier='encounter'
            )
            if defender:
                self._create_or_update_report(
                    defender,
                    'fleet',
                    fleet,
                    self.game.year,
                    report_tier='encounter',
                    include_cargo=self._player_has_advanced_scanner_at(defender, star.x, star.y),
                )

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
            ).exclude(player=defender).exclude(player__isnull=True).exclude(player__defeated=True)

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
        stance_scale = player_permission_value(
            defender,
            attacker,
            PERMISSION_ORBITAL_DEFENSE_CHANCE_SCALE,
            default=1.0,
            stance_map=self._stance_map_for_player(defender),
        )
        try:
            chance *= max(0.0, float(stance_scale))
        except (TypeError, ValueError):
            chance *= 1.0
        chance *= combined_diplomacy_chance_scale(defender, attacker)
        chance = max(0.0, min(1.0, chance))
        if chance <= 0.0:
            return
        if not roll_chance(chance):
            return

        defender_defence_mult = self._get_colony_defense_multiplier(defender, star)

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
                self.game, attacker, star, fleet, integrity_lost, perspective='attacker'
        ).new_message()
        attacker_msg.year = self.game.year
        attacker_msg.save()

        defender_msg = OrbitalDefenseHitMessageFactory(
                self.game, defender, star, fleet, integrity_lost, perspective='defender'
        ).new_message()
        defender_msg.year = self.game.year
        defender_msg.save()

    def _build_transfer_raid_resource_desc(self, fleet, order):
        labels = []
        for key in ALL_RESOURCE_KEYS:
            requested = int(getattr(order, f'transfer_{key}', 0) or 0)
            if requested <= 0:
                continue
            if key in SECRET_RESOURCE_KEYS:
                discovered = bool(getattr(fleet.player, f'discovered_{key}', False))
                labels.append(get_secret_resource_label(key, discovered))
            else:
                labels.append(key.title())
        if int(getattr(order, 'transfer_colonists', 0) or 0) > 0:
            labels.append('Colonists')
        return format_readable_list(labels) or 'supplies'

    def _resolve_transfer_raid_defense_fire(self, star, fleet):
        """Apply heavier, luck-weighted defense fire for theft attempts."""
        damage_multiplier = random.uniform(
            THEFT_DEFENSE_DAMAGE_MIN_MULTIPLIER,
            THEFT_DEFENSE_DAMAGE_MAX_MULTIPLIER,
        )
        luck_multiplier = float(getattr(fleet.player.race_type, 'luck_multiplier', 1.0) or 1.0)
        jitter = random.uniform(-THEFT_LUCK_JITTER, THEFT_LUCK_JITTER) * luck_multiplier
        damage_multiplier = max(0.1, damage_multiplier * (1.0 + jitter))
        return self._resolve_planetary_defense_fire_against_fleet(
            star, fleet, damage_multiplier=damage_multiplier
        )

    def _transfer_raid_success_chance(self, star, fleet, defense_fire):
        defender = star.player
        defender_defence_mult = self._get_colony_defense_multiplier(defender, star)
        attacker_strength = calculate_fleet_strength(fleet, defender_defence_mult)
        defender_strength = normalize_ship_count(calculate_effective_defenses(star))
        attacker_luck = float(getattr(fleet.player.race_type, 'luck_multiplier', 1.0) or 1.0)
        defender_luck = float(getattr(defender.race_type, 'luck_multiplier', 1.0) or 1.0)
        integrity_lost = int(defense_fire.get('integrity_lost', 0) or 0)
        ships_lost = int(defense_fire.get('ships_lost', 0) or 0)
        ship_count = int(fleet.ship_count or 0)
        return transfer_raid_success_chance(
            attacker_strength=attacker_strength,
            defender_strength=defender_strength,
            attacker_luck=attacker_luck,
            defender_luck=defender_luck,
            integrity_lost=integrity_lost,
            ships_lost=ships_lost,
            ship_count=ship_count,
            damage_weight=THEFT_SUCCESS_DAMAGE_WEIGHT,
            ship_weight=THEFT_SUCCESS_SHIP_WEIGHT,
            min_chance=THEFT_SUCCESS_MIN_CHANCE,
            max_chance=THEFT_SUCCESS_MAX_CHANCE,
        )

    def _transfer_raid_successful(self, star, fleet, defense_fire):
        chance = self._transfer_raid_success_chance(star, fleet, defense_fire)
        return chance_roll(chance)

    def _create_transfer_raid_messages(self, attacker, defender, fleet, star, resource_desc, damage_pct):
        if attacker:
            msg = TransferRaidThwartedMessageFactory(
                self.game,
                attacker,
                fleet=fleet,
                star=star,
                owner_name=getattr(defender, 'plural_name', None) or getattr(defender, 'name', ''),
                resource_desc=resource_desc,
                damage=damage_pct,
                perspective='attacker',
            ).new_message()
            msg.year = self.game.year
            msg.save()
        if defender:
            msg = TransferRaidThwartedMessageFactory(
                self.game,
                defender,
                fleet=fleet,
                star=star,
                owner_name=getattr(defender, 'plural_name', None) or getattr(defender, 'name', ''),
                resource_desc=resource_desc,
                damage=damage_pct,
                perspective='defender',
            ).new_message()
            msg.year = self.game.year
            msg.save()

    def _transfer_with_star(self, fleet, order, star):
        """Execute transfer between fleet and star."""
        fleet_max_capacity = fleet.cargo_capacity  # Use fleet's actual capacity
        resource_keys = ALL_RESOURCE_KEYS

        if order.transfer_type == 'LOAD':
            # Load from star to fleet
            total_requested = sum(
                int(getattr(order, f'transfer_{key}', 0) or 0) for key in resource_keys
            ) + int(order.transfer_colonists or 0)

            if total_requested == 0:
                return

            if star.player and star.player != fleet.player:
                defender = star.player
                attacker = fleet.player
                defender_stance_map = self._stance_map_for_player(defender)
                allow_defense = player_grants_permission(
                    defender,
                    attacker,
                    PERMISSION_ALLOW_TRANSFER_RAID_DEFENSE,
                    stance_map=defender_stance_map,
                )
                allow_roll = player_grants_permission(
                    defender,
                    attacker,
                    PERMISSION_ALLOW_TRANSFER_RAID_ROLL,
                    stance_map=defender_stance_map,
                )

                defense_fire = {
                    'destroyed': False,
                    'integrity_lost': 0,
                    'ships_lost': 0,
                    'defense_mult': 1.0,
                }
                if allow_defense:
                    defense_fire = self._resolve_transfer_raid_defense_fire(star, fleet)
                if defense_fire.get('destroyed'):
                    damage_pct = 100
                    resource_desc = self._build_transfer_raid_resource_desc(fleet, order)
                    self._create_transfer_raid_messages(
                        attacker, defender, fleet, star, resource_desc, damage_pct
                    )
                    return 'fleet_destroyed'
                if allow_roll and not self._transfer_raid_successful(star, fleet, defense_fire):
                    damage_pct = max(0, int(defense_fire.get('integrity_lost', 0) or 0))
                    resource_desc = self._build_transfer_raid_resource_desc(fleet, order)
                    self._create_transfer_raid_messages(
                        attacker, defender, fleet, star, resource_desc, damage_pct
                    )
                    return

            fleet_available = fleet_max_capacity - fleet.cargo_used
            total_transfer = min(fleet_available, total_requested)

            if total_transfer <= 0:
                return

            transfer_factor = total_transfer / float(total_requested)
            transfers = {}
            for key in resource_keys:
                requested = int(getattr(order, f'transfer_{key}', 0) or 0)
                available = int(getattr(star, f'{key}_inventory', 0) or 0)
                transfers[key] = min(int(requested * transfer_factor), available)

            colonists_transfer_kt = int((order.transfer_colonists or 0) * transfer_factor)
            colonists_transfer_individuals = min(colonists_transfer_kt * 1000, int(star.colonists or 0))
            colonists_transfer_kt_actual = colonists_transfer_individuals // 1000

            for key in resource_keys:
                setattr(
                    star,
                    f'{key}_inventory',
                    int(getattr(star, f'{key}_inventory', 0) or 0) - transfers[key]
                )
                setattr(
                    fleet,
                    f'{key}_inventory',
                    int(getattr(fleet, f'{key}_inventory', 0) or 0) + transfers[key]
                )

            star.colonists -= colonists_transfer_individuals
            fleet.colonists += colonists_transfer_kt_actual

            star.save()
            fleet.save()

            self._discover_secret_resources_from_star(fleet.player, star, fleet=fleet)

        elif order.transfer_type in ('UNLOAD', 'UNLOAD_ALL'):
            # Unload from fleet to star
            foreign_owner_before = star.player if star.player and star.player != fleet.player else None
            transfers = {}
            if order.transfer_type == 'UNLOAD_ALL':
                for key in resource_keys:
                    transfers[key] = int(getattr(fleet, f'{key}_inventory', 0) or 0)
                colonists_transfer_kt = int(fleet.colonists or 0)
            else:
                for key in resource_keys:
                    requested = int(getattr(order, f'transfer_{key}', 0) or 0)
                    available = int(getattr(fleet, f'{key}_inventory', 0) or 0)
                    transfers[key] = min(requested, available)
                colonists_transfer_kt = min(int(order.transfer_colonists or 0), int(fleet.colonists or 0))

            if colonists_transfer_kt > 0 and star.player is None:
                if random.random() < 0.10:
                    star.player = fleet.player
                    factory = ColonistsUnexpectedColonyMessageFactory(
                    self.game, fleet.player, fleet, colonists_transfer_kt, star
                    )
                    msg = factory.new_message()
                    msg.year = self.game.year
                    msg.save()
                else:
                    fleet.colonists -= colonists_transfer_kt
                    factory = ColonistsFailedToColoniseMessageFactory(
                    self.game, fleet.player, fleet, colonists_transfer_kt, star
                    )
                    msg = factory.new_message()
                    msg.year = self.game.year
                    msg.save()
                    colonists_transfer_kt = 0

            if colonists_transfer_kt > 0 and star.player and star.player != fleet.player:
                self._handle_invasion(fleet, star, colonists_transfer_kt)
                fleet.colonists -= colonists_transfer_kt
                colonists_transfer_kt = 0

            colonists_transfer_individuals = colonists_transfer_kt * 1000

            for key in resource_keys:
                setattr(
                    fleet,
                    f'{key}_inventory',
                    int(getattr(fleet, f'{key}_inventory', 0) or 0) - transfers[key]
                )
                setattr(
                    star,
                    f'{key}_inventory',
                    int(getattr(star, f'{key}_inventory', 0) or 0) + transfers[key]
                )

            fleet.colonists -= colonists_transfer_kt
            star.colonists += colonists_transfer_individuals

            star.save()
            fleet.save()

            if (
                foreign_owner_before is not None and
                star.player_id == foreign_owner_before.id and
                any(transfers.values())
            ):
                gift_factory = MineralGiftMessageFactory(
                    self.game,
                    foreign_owner_before,
                    fleet,
                    star,
                    transfers,
                )
                gift_msg = gift_factory.new_message()
                gift_msg.year = self.game.year
                gift_msg.save()
                apply_world_resource_delivery(
                    fleet.player,
                    foreign_owner_before,
                    transfers,
                    self.game.year,
                    star=star,
                )

            if star.player:
                self._discover_secret_resources_from_star(star.player, star)

    def _transfer_with_fleet(self, source_fleet, order, target_fleet):
        """Execute transfer between two fleets.

        Both fleets store colonists in thousands (1 unit = 1000 colonists),
        so no unit conversion is needed for fleet-to-fleet transfers.
        """
        resource_keys = ALL_RESOURCE_KEYS
        if order.transfer_type == 'LOAD':
            total_requested = sum(
                int(getattr(order, f'transfer_{key}', 0) or 0) for key in resource_keys
            ) + int(order.transfer_colonists or 0)

            if total_requested == 0:
                return

            source_available = source_fleet.cargo_capacity - source_fleet.cargo_used
            total_transfer = min(source_available, total_requested)
            if total_transfer <= 0:
                return

            transfer_factor = total_transfer / float(total_requested)
            transfers = {}
            for key in resource_keys:
                requested = int(getattr(order, f'transfer_{key}', 0) or 0)
                available = int(getattr(target_fleet, f'{key}_inventory', 0) or 0)
                transfers[key] = min(int(requested * transfer_factor), available)
            colonists_transfer = min(
                int((order.transfer_colonists or 0) * transfer_factor),
                int(target_fleet.colonists or 0)
            )

            for key in resource_keys:
                setattr(
                    target_fleet,
                    f'{key}_inventory',
                    int(getattr(target_fleet, f'{key}_inventory', 0) or 0) - transfers[key]
                )
                setattr(
                    source_fleet,
                    f'{key}_inventory',
                    int(getattr(source_fleet, f'{key}_inventory', 0) or 0) + transfers[key]
                )
            target_fleet.colonists -= colonists_transfer
            source_fleet.colonists += colonists_transfer

            target_fleet.save()
            source_fleet.save()
            self._discover_secret_resources_from_fleet(source_fleet.player, source_fleet)
        else:  # UNLOAD or UNLOAD_ALL
            transfers = {}
            if order.transfer_type == 'UNLOAD_ALL':
                for key in resource_keys:
                    transfers[key] = int(getattr(source_fleet, f'{key}_inventory', 0) or 0)
                colonists_transfer = int(source_fleet.colonists or 0)
            else:
                for key in resource_keys:
                    requested = int(getattr(order, f'transfer_{key}', 0) or 0)
                    available = int(getattr(source_fleet, f'{key}_inventory', 0) or 0)
                    transfers[key] = min(requested, available)
                colonists_transfer = min(int(order.transfer_colonists or 0), int(source_fleet.colonists or 0))

            target_available = target_fleet.cargo_capacity - target_fleet.cargo_used
            total_transfer = sum(transfers.values()) + colonists_transfer
            if total_transfer > target_available:
                if target_available <= 0:
                    return
                scale_factor = target_available / float(total_transfer)
                for key in resource_keys:
                    transfers[key] = int(transfers[key] * scale_factor)
                colonists_transfer = int(colonists_transfer * scale_factor)

            for key in resource_keys:
                setattr(
                    source_fleet,
                    f'{key}_inventory',
                    int(getattr(source_fleet, f'{key}_inventory', 0) or 0) - transfers[key]
                )
                setattr(
                    target_fleet,
                    f'{key}_inventory',
                    int(getattr(target_fleet, f'{key}_inventory', 0) or 0) + transfers[key]
                )
            source_fleet.colonists -= colonists_transfer
            target_fleet.colonists += colonists_transfer

            source_fleet.save()
            target_fleet.save()
            self._discover_secret_resources_from_fleet(target_fleet.player, target_fleet)

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
        if all(
            int(getattr(order, f'transfer_{key}', 0) or 0) == 0
            for key in ALL_RESOURCE_KEYS
        ):
            # Load all salvage, respecting capacity
            total_salvage = salvage.total_minerals
            if total_salvage == 0:
                return

            transfers = {}
            if total_salvage <= fleet_available:
                for key in ALL_RESOURCE_KEYS:
                    transfers[key] = int(getattr(salvage, f'{key}_inventory', 0) or 0)
            else:
                ratio = fleet_available / float(total_salvage)
                for key in ALL_RESOURCE_KEYS:
                    transfers[key] = int((getattr(salvage, f'{key}_inventory', 0) or 0) * ratio)
        else:
            # Transfer requested amounts (limited by available)
            total_requested = sum(
                int(getattr(order, f'transfer_{key}', 0) or 0) for key in ALL_RESOURCE_KEYS
            )
            if total_requested == 0:
                return

            # Limit by fleet available space
            total_transfer = min(fleet_available, total_requested)
            if total_transfer <= 0:
                return

            # Calculate proportional transfers
            transfer_factor = total_transfer / total_requested
            transfers = {}
            for key in ALL_RESOURCE_KEYS:
                transfers[key] = min(
                    int(getattr(order, f'transfer_{key}', 0) or 0) * transfer_factor,
                    int(getattr(salvage, f'{key}_inventory', 0) or 0)
                )
            transfers = {key: int(val) for key, val in transfers.items()}

        # Execute the transfer
        for key in ALL_RESOURCE_KEYS:
            setattr(
                salvage,
                f'{key}_inventory',
                int(getattr(salvage, f'{key}_inventory', 0) or 0) - transfers[key]
            )
            setattr(
                fleet,
                f'{key}_inventory',
                int(getattr(fleet, f'{key}_inventory', 0) or 0) + transfers[key]
            )

        fleet.save()

        source_label = format_map_object(
            salvage,
            link=salvage.total_minerals > 0,
        )

        # Delete salvage if emptied, otherwise save
        if salvage.total_minerals == 0:
            salvage.delete()
        else:
            salvage.save()

        # Create collection message if anything was transferred
        if any(transfers.values()):
            factory = SalvageCollectedMessageFactory(
                self.game, fleet.player, fleet, transfers, source_label
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()

        for key in SECRET_RESOURCE_KEYS:
            if int(transfers.get(key, 0) or 0) > 0:
                self._mark_secret_resource_discovered(
                    fleet.player, key, star=salvage, fleet=fleet, source=salvage
                )
        self._discover_secret_resources_from_fleet(fleet.player, fleet)

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

    def _get_colony_defense_multiplier(self, defender, star):
        """Return colony defense multiplier including tech and fixed homeworld bonus."""
        if defender is None:
            return 1.0
        raw_defence_mult = getattr(defender.race_type, 'defence_multiplier', 1.0)
        if raw_defence_mult is None:
            raw_defence_mult = 1.0
        defender_defence_mult = float(raw_defence_mult)
        defender_defence_mult *= tech_level_to_multiplier(get_player_colony_defense_level(defender))
        if star is not None and bool(getattr(defender, 'fixed_homeworld', False)):
            if int(getattr(defender, 'homeworld_id', 0) or 0) == int(getattr(star, 'id', 0) or 0):
                defender_defence_mult *= 1.5
        return defender_defence_mult

    def _resolve_planetary_defense_fire_against_fleet(self, star, fleet, damage_multiplier=1.0):
        """Apply colony defense fire to a hostile fleet before bombardment."""
        if not star.player or star.player == fleet.player:
            return {'destroyed': False, 'integrity_lost': 0, 'ships_lost': 0, 'defense_mult': 1.0}

        effective_defenses = calculate_effective_defenses(star)
        if effective_defenses <= 0:
            return {'destroyed': False, 'integrity_lost': 0, 'ships_lost': 0, 'defense_mult': 1.0}

        defender = star.player
        defender_defence_mult = self._get_colony_defense_multiplier(defender, star)

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
                self.game, fleet.player, fleet, target_x, target_y
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
                star=star,
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
            'has_administration': bool(getattr(star, 'has_administration', False)),
            'has_dyson_sphere': bool(getattr(star, 'has_dyson_sphere', False)),
        }
        effective_defenses = max(0.0, float(calculate_effective_defenses(star)))
        luck_multiplier = float(getattr(fleet.player.race_type, 'luck_multiplier', 1.0) or 1.0)
        raw_bombardment_multiplier = getattr(
            fleet.player.race_type,
            'bombardment_multiplier',
            1.0,
        )
        if raw_bombardment_multiplier is None:
            bombardment_multiplier = 1.0
        else:
            bombardment_multiplier = float(raw_bombardment_multiplier)
        damage_k = bombardment_damage_k(
            fleet.ship_count,
            fleet.offense_level,
            effective_defenses * defense_fire.get('defense_mult', 1.0),
            luck_multiplier,
            bomb_type,
        )
        damage_k = max(0, int(round(damage_k * bombardment_multiplier)))

        defenses_lost = min(pre['defenses'], damage_k)
        colonists_lost = min(pre['colonists'], damage_k * 1000)
        star.defenses = max(0, pre['defenses'] - defenses_lost)
        star.colonists = max(0, pre['colonists'] - colonists_lost)

        mines_lost = 0
        factories_lost = 0
        labs_lost = 0
        shipyards_lost = 0
        administration_lost = 0
        dyson_sphere_lost = 0
        if not smart_bombs_only_target_defenses_and_population(bomb_type):
            mines_lost = min(pre['mines'], damage_k)
            factories_lost = min(pre['factories'], damage_k)
            labs_lost = min(pre['labs'], damage_k)
            shipyards_lost = min(pre['shipyards'], damage_k)
            if pre['has_administration'] and damage_k > 0:
                administration_lost = 1
            if pre['has_dyson_sphere'] and damage_k > 0:
                dyson_sphere_lost = 1
            star.mines = max(0, pre['mines'] - mines_lost)
            star.factories = max(0, pre['factories'] - factories_lost)
            star.labs = max(0, pre['labs'] - labs_lost)
            star.shipyards = max(0, pre['shipyards'] - shipyards_lost)
            if administration_lost:
                star.has_administration = False
            if dyson_sphere_lost:
                star.has_dyson_sphere = False

        star_destroyed = False
        destroyed_star_name = star.name
        if bomb_type == 'NOVA' and roll_chance(NOVA_STAR_DESTRUCTION_CHANCE):
            star_destroyed = True
            star_snapshot = self._snapshot_star_for_nova_remnant(star)
            destroyed_x = star.x
            destroyed_y = star.y
            destroyed_owner_id = star.player_id
            destroyed_star_id = star.id
            destroyed_star_short_id = star.short_id
            star.delete()
            if destroyed_owner_id:
                from .models import Player
                lost_player = Player.objects.filter(id=destroyed_owner_id).first()
                if lost_player:
                    self._handle_homeworld_loss(
                        lost_player,
                        lost_star_id=destroyed_star_id,
                        location=(destroyed_x, destroyed_y),
                    )
            self._retarget_or_remove_orders_for_destroyed_star(
                destroyed_star_id, destroyed_star_short_id, destroyed_x, destroyed_y,
                preserve_order_id=order.id
            )
            self._notify_star_vanished(
                destroyed_star_name, destroyed_x, destroyed_y, fleet,
                former_owner_id=destroyed_owner_id
            )
            self._create_nova_star_remnant(star_snapshot)
        else:
            star.save(update_fields=[
                'defenses', 'colonists', 'mines', 'factories', 'labs',
                'shipyards', 'has_administration', 'has_dyson_sphere',
            ])

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
            administration_lost=administration_lost,
            dyson_sphere_lost=dyson_sphere_lost,
            integrity_lost=defense_fire.get('integrity_lost', 0),
            ships_lost=defense_fire.get('ships_lost', 0),
            star_destroyed=star_destroyed,
            star=None if star_destroyed else star,
        )
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()

        if defending_player is not None:
            total_losses = (
                defenses_lost + colonists_lost +
                mines_lost + factories_lost + labs_lost + shipyards_lost +
                administration_lost + dyson_sphere_lost
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
                    administration_lost=administration_lost,
                    dyson_sphere_lost=dyson_sphere_lost,
                    integrity_lost=defense_fire.get('integrity_lost', 0),
                    ships_lost=defense_fire.get('ships_lost', 0),
                    star_destroyed=star_destroyed,
                    perspective='defender',
                    attacker_fleet_name=fleet.name,
                    star=None if star_destroyed else star,
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

    def _snapshot_star_for_nova_remnant(self, star):
        """Capture star mineral and yield state before nova destruction."""
        if star is None:
            return None
        snapshot = {
            'x': int(star.x),
            'y': int(star.y),
        }
        for key in ALL_RESOURCE_KEYS:
            snapshot['%s_yield' % key] = int(getattr(star, '%s_yield' % key, 0) or 0)
            snapshot['%s_inventory' % key] = int(
                getattr(star, '%s_inventory' % key, 0) or 0
            )
        return snapshot

    def _stars_remain_at_location(self, x, y):
        """Return True if any star in this game still exists at the coordinate."""
        from .models import Star
        try:
            x = int(x)
            y = int(y)
        except (TypeError, ValueError):
            return False
        return Star.objects.filter(game=self.game, x=x, y=y).exists()

    def _create_nova_star_remnant(self, star_snapshot):
        """Create a black hole or asteroid field after nova star destruction."""
        if not star_snapshot:
            return None
        x = int(star_snapshot.get('x', 0) or 0)
        y = int(star_snapshot.get('y', 0) or 0)
        if self._stars_remain_at_location(x, y):
            return None
        if self._maybe_spawn_black_hole_from_nova(x, y):
            return 'black_hole'
        if roll_chance(NOVA_ASTEROID_FIELD_SPAWN_CHANCE):
            salvage = self._create_asteroid_field_from_nova(star_snapshot)
            if salvage is not None:
                return salvage
        return None

    def _maybe_spawn_black_hole_from_nova(self, x, y):
        """Create a black hole at a nova-destroyed star location when it rolls."""
        if not roll_chance(NOVA_BLACK_HOLE_SPAWN_CHANCE):
            return None
        if self._stars_remain_at_location(x, y):
            return None
        from .models import Anomaly
        if Anomaly.objects.filter(game=self.game, x=x, y=y).exists():
            return None
        return Anomaly.objects.create(
            game=self.game,
            x=int(x),
            y=int(y),
            anomaly_type=Anomaly.TYPE_BLACK_HOLE,
            name='Black Hole %s' % (Anomaly.objects.filter(game=self.game).count() + 1),
            heading=random.random() * 360.0,
            stability=random.randint(30, 91),
        )

    def _nova_exposed_minerals_from_yield(self, yield_pct):
        """Expose a recoverable fraction of a star's long-term mineral potential."""
        try:
            yield_pct = int(yield_pct or 0)
        except (TypeError, ValueError):
            yield_pct = 0
        if yield_pct <= 0:
            return 0
        potential_kt = float(yield_pct) / float(YIELD_DEPLETION_RATE)
        exposed = potential_kt * float(NOVA_ASTEROID_FIELD_EXPOSED_POTENTIAL_FRACTION)
        return max(0, int(round(exposed)))

    def _create_asteroid_field_from_nova(self, star_snapshot):
        """Create or enrich an asteroid field with surface and exposed deep minerals."""
        from .models import Salvage

        x = int(star_snapshot.get('x', 0) or 0)
        y = int(star_snapshot.get('y', 0) or 0)
        if self._stars_remain_at_location(x, y):
            return None
        minerals = {}
        for key in ALL_RESOURCE_KEYS:
            surface = int(star_snapshot.get('%s_inventory' % key, 0) or 0)
            yield_pct = int(star_snapshot.get('%s_yield' % key, 0) or 0)
            minerals[key] = surface + self._nova_exposed_minerals_from_yield(yield_pct)

        if sum(int(value or 0) for value in minerals.values()) <= 0:
            return None

        salvage, created = Salvage.objects.get_or_create(
            game=self.game,
            x=x,
            y=y,
            defaults={
                'salvage_type': Salvage.TYPE_ASTEROID_FIELD,
                'ironium_inventory': int(minerals.get('ironium', 0) or 0),
                'boranium_inventory': int(minerals.get('boranium', 0) or 0),
                'germanium_inventory': int(minerals.get('germanium', 0) or 0),
                'resource_x_inventory': int(minerals.get('resource_x', 0) or 0),
                'resource_y_inventory': int(minerals.get('resource_y', 0) or 0),
                'resource_z_inventory': int(minerals.get('resource_z', 0) or 0),
            }
        )
        if created:
            return salvage

        salvage.salvage_type = Salvage.TYPE_ASTEROID_FIELD
        for key in ALL_RESOURCE_KEYS:
            field = '%s_inventory' % key
            current = int(getattr(salvage, field, 0) or 0)
            setattr(salvage, field, current + int(minerals.get(key, 0) or 0))
        salvage.save()
        return salvage

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

    def _retarget_or_remove_orders_for_destroyed_star(
        self, destroyed_star_id, destroyed_star_short_id, x, y, preserve_order_id=None
    ):
        """Convert movement targets to coordinates and remove other orders."""
        from .models import FleetOrders
        from django.db.models import Q

        orders = FleetOrders.objects.filter(
            game=self.game
        ).filter(
            Q(target_star_id=destroyed_star_id) |
            Q(target_kind='OBJECT', target_short_id=destroyed_star_short_id)
        )
        if preserve_order_id is not None:
            orders = orders.exclude(id=preserve_order_id)

        movement_types = ['MOVE', 'INTERCEPT', 'PATROL']
        orders.filter(order_type__in=movement_types).update(
            target_star=None,
            target_kind='SPACE',
            target_short_id=None,
            x=int(x),
            y=int(y),
        )
        orders.exclude(order_type__in=movement_types).delete()

    def _try_execute_remote_mine(self, fleet, order):
        """Try to execute a remote mining order at the targeted star."""
        _, dest_x, dest_y, kind = order.get_actual_target()
        if kind == 'none':
            order.delete()
            return 'executed'
        if fleet.x != dest_x or fleet.y != dest_y:
            return 'waiting'
        return self._execute_remote_mine_order(fleet, order)

    def _extract_minerals_with_standard_rules(
        self,
        star,
        total_extraction,
        resource_keys=None,
        total_extraction_for_depletion=None,
    ):
        """Extract minerals from a star using standard mining/depletion mechanics.

        Returns per-resource extracted whole kt:
        {'ironium': int, 'boranium': int, 'germanium': int, 'resource_x': int, ...}
        and updates star yield fields in-place.
        """
        if resource_keys is None:
            resource_keys = ALL_RESOURCE_KEYS
        else:
            resource_keys = [key for key in resource_keys if key in ALL_RESOURCE_KEYS]
        total_extraction = max(0.0, float(total_extraction or 0.0))
        if total_extraction_for_depletion is None:
            total_extraction_for_depletion = total_extraction
        total_extraction_for_depletion = max(
            0.0, float(total_extraction_for_depletion or 0.0)
        )
        produced = {key: 0 for key in ALL_RESOURCE_KEYS}
        if total_extraction <= 0:
            return produced

        if not resource_keys:
            return produced

        total_yield = sum(
            int(getattr(star, f'{key}_yield', 0) or 0) for key in resource_keys
        )
        if total_yield <= 0:
            return produced

        is_homeworld = star.homeworld_of.exists()
        min_yield = HOMEWORLD_MIN_YIELD if is_homeworld else 0

        for key in resource_keys:
            resource = f'{key}_yield'
            yield_val = int(getattr(star, resource, 0) or 0)
            if yield_val <= 0:
                continue

            extraction = total_extraction * yield_val / total_yield
            depletion_extraction = (
                total_extraction_for_depletion * yield_val / total_yield
            )
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
                (float(depletion_extraction) - sustainable_extraction) / sustainable_extraction
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

    def _parse_remotemine_focus_keys(self, order):
        raw = (getattr(order, 'remotemine_focus', '') or '').strip()
        if not raw:
            return []
        parts = [
            part.strip().lower()
            for part in raw.replace(';', ',').split(',')
            if part.strip()
        ]
        return [key for key in parts if key in ALL_RESOURCE_KEYS]

    def _get_remotemine_focus_keys(self, order, fleet):
        if not order or not fleet:
            return ALL_RESOURCE_KEYS
        miner_type = normalize_miner_type(getattr(fleet, 'has_miners', None))
        if miner_type != 'LARGE':
            return ALL_RESOURCE_KEYS
        keys = self._parse_remotemine_focus_keys(order)
        if not keys:
            return ALL_RESOURCE_KEYS
        return keys

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
        focus_keys = self._get_remotemine_focus_keys(order, fleet)
        produced = self._extract_minerals_with_standard_rules(
            star,
            total_extraction,
            resource_keys=focus_keys,
        )

        remaining_capacity = max(0, int(fleet.cargo_remaining or 0))
        fleet_added = {}
        surface_added = {}
        for key in ALL_RESOURCE_KEYS:
            amount = int(produced.get(key, 0) or 0)
            take = min(amount, remaining_capacity)
            remaining_capacity -= take
            fleet_added[key] = take
            surface_added[key] = amount - take

        for key in ALL_RESOURCE_KEYS:
            setattr(fleet, f'{key}_inventory', int(getattr(fleet, f'{key}_inventory', 0) or 0) + fleet_added[key])
            setattr(star, f'{key}_inventory', int(getattr(star, f'{key}_inventory', 0) or 0) + surface_added[key])

        fleet.save(update_fields=[f'{key}_inventory' for key in ALL_RESOURCE_KEYS])
        star.save(update_fields=[
            *[f'{key}_inventory' for key in ALL_RESOURCE_KEYS],
            'defenses', 'colonists', 'mines', 'factories', 'labs', 'shipyards',
            *[f'{key}_yield' for key in ALL_RESOURCE_KEYS],
        ])

        self._discover_secret_resources_from_star(fleet.player, star, fleet=fleet)

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

        # Get the target star. Handle stale target_star references safely.
        target_obj, dest_x, dest_y, target_kind = order.get_actual_target()
        star = target_obj if target_kind == 'star' else None
        if star is None:
            # Look for star at the resolved destination coordinates.
            star = Star.objects.filter(game=self.game, x=dest_x, y=dest_y).first()

        if not star:
            # No star at location, cannot colonise - create message and delete order
            factory = ColoniseFailedNoStarMessageFactory(
                self.game, fleet.player, fleet, dest_x, dest_y,
                target_star=None
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
                fleet,
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
                self.game, fleet.player, fleet, star
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
        resource_x = fleet.resource_x_inventory
        resource_y = fleet.resource_y_inventory
        resource_z = fleet.resource_z_inventory
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
        if resource_x > 0:
            cargo_parts.append(f"{resource_x}kt {get_secret_resource_name('resource_x')}")
        if resource_y > 0:
            cargo_parts.append(f"{resource_y}kt {get_secret_resource_name('resource_y')}")
        if resource_z > 0:
            cargo_parts.append(f"{resource_z}kt {get_secret_resource_name('resource_z')}")
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
            star.resource_x_inventory += resource_x
            star.resource_y_inventory += resource_y
            star.resource_z_inventory += resource_z
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

            self._discover_secret_resources_from_star(player, star, fleet=fleet)

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
        weighted_warp_advantage = (
            (float(source_fleet.warp_advantage or 0.0) * source_fleet.ship_count) +
            (float(target_fleet.warp_advantage or 0.0) * target_fleet.ship_count)
        ) / float(total_ships)
        source_has_wormhole_drive = bool(source_fleet.has_wormhole_drive)
        target_has_wormhole_drive = bool(target_fleet.has_wormhole_drive)
        merged_has_wormhole_drive = bool(
            source_has_wormhole_drive or target_has_wormhole_drive
        )
        merged_wormhole_fuel_per_ly = float(
            target_fleet.wormhole_fuel_per_ly or 5.0
        )
        merged_wormhole_destruction = float(
            target_fleet.wormhole_destruction_chance or 0.0
        )
        if source_has_wormhole_drive and target_has_wormhole_drive:
            merged_wormhole_fuel_per_ly = (
                (float(source_fleet.wormhole_fuel_per_ly or 5.0) * source_fleet.ship_count) +
                (float(target_fleet.wormhole_fuel_per_ly or 5.0) * target_fleet.ship_count)
            ) / float(total_ships)
            merged_wormhole_destruction = (
                (
                    float(source_fleet.wormhole_destruction_chance or 0.0) *
                    source_fleet.ship_count
                ) +
                (
                    float(target_fleet.wormhole_destruction_chance or 0.0) *
                    target_fleet.ship_count
                )
            ) / float(total_ships)
        elif source_has_wormhole_drive:
            merged_wormhole_fuel_per_ly = float(
                source_fleet.wormhole_fuel_per_ly or 5.0
            )
            merged_wormhole_destruction = float(
                source_fleet.wormhole_destruction_chance or 0.0
            )

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
        target_fleet.warp_advantage = weighted_warp_advantage
        target_fleet.wormhole_fuel_per_ly = merged_wormhole_fuel_per_ly
        target_fleet.wormhole_destruction_chance = merged_wormhole_destruction
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
        target_fleet.fuel_factory_mg_per_year = max(
            float(getattr(target_fleet, 'fuel_factory_mg_per_year', 0.0) or 0.0),
            float(getattr(source_fleet, 'fuel_factory_mg_per_year', 0.0) or 0.0),
        )
        target_fleet.fuel_factory_max_warp = max(
            int(getattr(target_fleet, 'fuel_factory_max_warp', -1) or 0),
            int(getattr(source_fleet, 'fuel_factory_max_warp', -1) or 0),
        )
        target_fleet.has_fuel_factory = bool(
            target_fleet.fuel_factory_mg_per_year > 0.0
        )
        target_fleet.has_wormhole_drive = merged_has_wormhole_drive
        target_fleet.max_cloaked_warp = max(
            int(getattr(target_fleet, 'max_cloaked_warp', -1) or 0),
            int(getattr(source_fleet, 'max_cloaked_warp', -1) or 0),
        )
        target_fleet.advanced_cloak = bool(
            getattr(target_fleet, 'advanced_cloak', False) or
            getattr(source_fleet, 'advanced_cloak', False)
        )

        # Transfer cargo (may exceed capacity - intentional for merge)
        target_fleet.ironium_inventory += source_fleet.ironium_inventory
        target_fleet.boranium_inventory += source_fleet.boranium_inventory
        target_fleet.germanium_inventory += source_fleet.germanium_inventory
        target_fleet.resource_x_inventory += source_fleet.resource_x_inventory
        target_fleet.resource_y_inventory += source_fleet.resource_y_inventory
        target_fleet.resource_z_inventory += source_fleet.resource_z_inventory
        target_fleet.colonists += source_fleet.colonists

        target_fleet.save()

        # Update orders from other fleets that target the source fleet
        # Use explicit ID to avoid any object reference issues with CASCADE
        FleetOrders.objects.filter(target_fleet_id=source_fleet.id).update(
            target_fleet_id=target_fleet.id,
            target_kind='OBJECT',
            target_short_id=target_fleet.short_id,
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

    def _execute_give_order(self, fleet, order):
        """Transfer fleet ownership to another player or abandon it."""
        previous_owner = fleet.player
        if previous_owner is None:
            order.delete()
            return 'executed'

        fleet_name = fleet.name
        cargo_bundle = {
            'ironium': int(getattr(fleet, 'ironium_inventory', 0) or 0),
            'boranium': int(getattr(fleet, 'boranium_inventory', 0) or 0),
            'germanium': int(getattr(fleet, 'germanium_inventory', 0) or 0),
            'resource_x': int(getattr(fleet, 'resource_x_inventory', 0) or 0),
            'resource_y': int(getattr(fleet, 'resource_y_inventory', 0) or 0),
            'resource_z': int(getattr(fleet, 'resource_z_inventory', 0) or 0),
            'colonists': int(getattr(fleet, 'colonists', 0) or 0),
        }
        ship_count = int(getattr(fleet, 'ship_count', 0) or 0)
        recipient = order.transfer_player
        if recipient is not None and (
            recipient.game_id != self.game.id or bool(getattr(recipient, 'defeated', False))
        ):
            recipient = None

        if recipient is not None and recipient.id == previous_owner.id:
            order.delete()
            return 'executed'

        if recipient is None:
            self._abandon_fleet(fleet)
        else:
            self._capture_fleet(fleet, recipient)
            apply_give_fleet_delivery(
                previous_owner,
                recipient,
                fleet,
                cargo_bundle,
                ship_count,
                self.game.year,
            )

        self._create_or_update_report(
            previous_owner,
            'fleet',
            fleet,
            self.game.year,
            report_tier='encounter',
            include_cargo=True,
        )

        sender_msg = FleetTransferredMessageFactory(
            self.game,
            previous_owner,
            fleet,
            recipient_name=(recipient.name if recipient is not None else None),
        ).new_message()
        sender_msg.year = self.game.year
        sender_msg.save()

        if recipient is not None:
            recipient_msg = FleetReceivedMessageFactory(
                self.game,
                recipient,
                fleet,
                previous_owner.name,
            ).new_message()
            recipient_msg.year = self.game.year
            recipient_msg.save()

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
        if int(order.intercept_speed or 0) == WORMHOLE_WARPFACTOR:
            order.intercept_speed = 13
            order.save(update_fields=['intercept_speed'])

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
            order.original_warpfactor = order.intercept_speed
            order.overmax_risk_checked = False
            order.target_kind = 'OBJECT'
            order.target_short_id = enemy_fleet.short_id
            order.x = target_x
            order.y = target_y
            order.patrol_generated = True
            order.save(update_fields=[
                'order_type', 'target_fleet', 'target_kind', 'target_short_id',
                'warpfactor', 'original_warpfactor', 'overmax_risk_checked',
                'x', 'y', 'repeat', 'patrol_generated'
            ])
        else:
            order.order_type = 'MOVE'
            order.warpfactor = fleet.max_safe_warp
            order.original_warpfactor = fleet.max_safe_warp
            order.overmax_risk_checked = False
            order.target_fleet = None
            order.target_salvage = None
            order.target_star = None
            order.x = target_x
            order.y = target_y
            order.target_kind = 'SPACE'
            order.target_short_id = None
            order.patrol_generated = False
            order.save(update_fields=[
                'order_type', 'warpfactor', 'original_warpfactor', 'overmax_risk_checked',
                'target_fleet', 'target_salvage',
                'target_star', 'target_kind', 'target_short_id', 'x', 'y',
                'repeat', 'patrol_generated'
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
            target_kind=order.target_kind,
            target_short_id=order.target_short_id,
            target_star_id=order.target_star_id,
            target_fleet_id=order.target_fleet_id,
            target_salvage_id=order.target_salvage_id,
            patrol_generated=False,
            added_by_micromanager=bool(
                getattr(order, 'added_by_micromanager', False)
            ),
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
        sources = self._get_player_scanner_sources(player)
        for enemy in candidates:
            if not self._players_can_target_each_other(player, enemy.player):
                continue
            if not fleet_targetable_by_patrol(enemy, player, sources=sources):
                continue
            dx = enemy.x - x
            dy = enemy.y - y
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= radius and (nearest_dist is None or dist < nearest_dist):
                nearest = enemy
                nearest_dist = dist
        return nearest

    def _get_player_scanner_sources(self, player):
        if not player:
            return []
        sources = self._scanner_sources_by_player_id.get(player.id)
        if sources is None:
            sources = get_scanner_sources_for_player(self.game, player)
            self._scanner_sources_by_player_id[player.id] = sources
        return sources

    def _fleet_target_visible_to_player(self, player, target_fleet):
        if not player or not target_fleet:
            return False
        sources = self._get_player_scanner_sources(player)
        return fleet_visible_to_player(target_fleet, player, sources=sources)

    def _handle_hidden_fleet_target(self, fleet, order):
        target_fleet = order.target_fleet
        if not target_fleet:
            return False
        if self._fleet_target_visible_to_player(fleet.player, target_fleet):
            return False

        self._create_hidden_fleet_target_message(fleet.player, fleet, order, target_fleet)
        if bool(getattr(order, 'patrol_generated', False)):
            self._restore_patrol_generated_intercept(order, fleet)
        else:
            self._convert_hidden_fleet_target_to_empty_space(order, target_fleet)
        return False

    def _restore_patrol_generated_intercept(self, order, fleet):
        order.order_type = 'MOVE'
        order.target_fleet = None
        order.target_star = None
        order.target_salvage = None
        order.target_short_id = None
        order.target_kind = 'SPACE'
        order.warpfactor = fleet.max_safe_warp
        order.original_warpfactor = fleet.max_safe_warp
        order.overmax_risk_checked = False
        order.patrol_generated = False
        order.save(update_fields=[
            'order_type', 'target_fleet', 'target_star', 'target_salvage',
            'target_short_id', 'target_kind', 'warpfactor',
            'original_warpfactor', 'overmax_risk_checked', 'patrol_generated',
        ])

    def _convert_hidden_fleet_target_to_empty_space(self, order, target_fleet):
        last_known_x = order.x if order.x is not None else target_fleet.x
        last_known_y = order.y if order.y is not None else target_fleet.y
        order.order_type = 'MOVE'
        order.target_fleet = None
        order.target_star = None
        order.target_salvage = None
        order.target_short_id = None
        order.target_kind = 'SPACE'
        order.x = int(last_known_x)
        order.y = int(last_known_y)
        order.patrol_generated = False
        order.save(update_fields=[
            'order_type', 'target_fleet', 'target_star', 'target_salvage',
            'target_short_id', 'target_kind', 'x', 'y', 'patrol_generated',
        ])

    def _create_hidden_fleet_target_message(self, player, source_fleet, order, target_fleet):
        from .models import GameMessage

        verbs = [
            "lost track of",
            "lost sight of",
            "can no longer find",
        ]
        if bool(getattr(order, 'patrol_generated', False)):
            text = "%s %s its target %s and is returning to patrol." % (
                format_map_object(source_fleet),
                random.choice(verbs),
                target_fleet.name,
            )
        else:
            text = "%s %s target fleet %s and is continuing to last known coordinates at %s." % (
                format_map_object(source_fleet),
                random.choice(verbs),
                target_fleet.name,
                format_location(order.x if order.x is not None else target_fleet.x,
                                order.y if order.y is not None else target_fleet.y),
            )
        GameMessage.objects.create(
            game=self.game,
            player=player,
            year=self.game.year,
            category='GENERAL',
            message=text,
            priority=False,
        )

    def _find_patrol_enemy(self, player, x, y, radius, patrol_target_fleet):
        """Prefer enemy fleets other than the patrol target, if possible."""
        if patrol_target_fleet and patrol_target_fleet.player != player:
            if not self._players_can_target_each_other(player, patrol_target_fleet.player):
                patrol_target_fleet = None
            elif not self._fleet_target_visible_to_player(player, patrol_target_fleet):
                patrol_target_fleet = None
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
            raw_multiplier = getattr(player.race_type, 'population_growth_multiplier', 1.0)
            if raw_multiplier is None:
                raw_multiplier = 1.0
            factor *= float(
                raw_multiplier
            )
            if factor > 0 and bool(getattr(player.race_type, 'is_mechanical', False)):
                factor = 0.0
            star.colonists = apply_population_change(star.colonists, factor)
            if (
                factor > 0 and
                population_growth_uses_surface_resources(player)
            ):
                proposed_growth = max(0, star.colonists - old_pop)
                limited_growth, ironium_cost, boranium_cost = (
                    limit_population_growth_by_surface_resources(star, proposed_growth)
                )
                star.colonists = old_pop + limited_growth
                star.ironium_inventory = max(0, int(star.ironium_inventory or 0) - ironium_cost)
                star.boranium_inventory = max(0, int(star.boranium_inventory or 0) - boranium_cost)
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
            for owner in list(star.homeworld_of.all()):
                self._handle_homeworld_loss(
                    owner,
                    lost_star=star,
                    location=(star.x, star.y),
                )
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

    def _select_replacement_homeworld(self, player, exclude_star_id=None):
        from .models import Star
        candidates = []
        for star in Star.objects.filter(game=self.game, player=player):
            if exclude_star_id and int(star.id) == int(exclude_star_id):
                continue
            if int(star.colonists or 0) <= 0:
                continue
            if calculate_habitability_factor(player, star) < 0:
                continue
            candidates.append(star)
        if not candidates:
            return None
        return max(candidates, key=lambda s: (int(s.colonists or 0), int(s.id)))

    def _determine_defeat_victor(self, defeated_player, location=None):
        if not location:
            return None
        try:
            x, y = location
        except (TypeError, ValueError):
            return None
        from .models import Fleet
        fleets = list(Fleet.objects.filter(
            game=self.game,
            x=x,
            y=y,
            player__isnull=False,
            player__defeated=False,
        ).exclude(player=defeated_player))
        return self._strongest_player_for_fleets(fleets)

    def _roll_defeated_fleet_fate(self):
        roll = random.random()
        if roll < DEFEATED_FLEET_CAPTURE_CHANCE:
            return 'capture'
        if roll < (DEFEATED_FLEET_CAPTURE_CHANCE + DEFEATED_FLEET_SCUTTLE_CHANCE):
            return 'scuttle'
        return 'abandon'

    def _scuttle_defeated_fleet(self, fleet):
        self._create_salvage_from_fleet(fleet)
        fleet.delete()

    def _abandon_player_colonies(self, player, exclude_star_id=None):
        from .models import Star
        stars = Star.objects.filter(game=self.game, player=player)
        if exclude_star_id:
            stars = stars.exclude(id=exclude_star_id)
        for star in stars:
            self._create_colony_abandoned_message(player, star)
            star.production_orders.all().delete()
            star.player = None
            star.colonists = 0
            star.save(update_fields=['player', 'colonists'])

    def _resolve_defeated_player_fleets(self, player, victor):
        from .models import Fleet
        fleets = list(Fleet.objects.filter(game=self.game, player=player))
        if not fleets:
            return
        if victor is None:
            for fleet in fleets:
                self._abandon_fleet(fleet)
            return
        for fleet in fleets:
            fate = self._roll_defeated_fleet_fate()
            if fate == 'capture':
                self._capture_fleet(fleet, victor)
            elif fate == 'scuttle':
                self._scuttle_defeated_fleet(fleet)
            else:
                self._abandon_fleet(fleet)

    def _defeat_player(self, player, lost_star_id=None, location=None):
        if player is None or bool(getattr(player, 'defeated', False)):
            return
        player.defeated = True
        player.turned_in = True
        player.homeworld = None
        player.save(update_fields=['defeated', 'turned_in', 'homeworld'])
        victor = self._determine_defeat_victor(player, location=location)
        self._abandon_player_colonies(player, exclude_star_id=lost_star_id)
        self._resolve_defeated_player_fleets(player, victor)

    def _handle_homeworld_loss(self, player, lost_star=None, location=None, lost_star_id=None):
        if player is None or bool(getattr(player, 'defeated', False)):
            return
        star_id = lost_star_id or (lost_star.id if lost_star is not None else None)
        if star_id is not None:
            if int(getattr(player, 'homeworld_id', 0) or 0) != int(star_id):
                return
        if bool(getattr(player, 'fixed_homeworld', False)):
            self._defeat_player(player, lost_star_id=star_id, location=location)
            return
        replacement = self._select_replacement_homeworld(player, exclude_star_id=star_id)
        if replacement is not None:
            player.homeworld = replacement
            player.save(update_fields=['homeworld'])
            return
        self._defeat_player(player, lost_star_id=star_id, location=location)

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
            total_yield = sum(
                int(getattr(star, f'{key}_yield', 0) or 0) for key in ALL_RESOURCE_KEYS
            )
            if total_yield == 0:
                continue

            staffing_ratio = calculate_staffing_ratio(star)
            if staffing_ratio == 0:
                continue
            productivity = calculate_productivity_multiplier(staffing_ratio)
            base_extraction = star.mines * KT_PER_MINE * productivity
            total_extraction = base_extraction
            if has_active_dyson_sphere(star):
                total_extraction *= 3.0

            produced = self._extract_minerals_with_standard_rules(
                star,
                total_extraction,
                total_extraction_for_depletion=base_extraction,
            )
            for key in ALL_RESOURCE_KEYS:
                setattr(
                    star,
                    f'{key}_inventory',
                    int(getattr(star, f'{key}_inventory', 0) or 0) + int(produced.get(key, 0) or 0)
                )

            star.save()
            self._discover_secret_resources_from_star(star.player, star)

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
        8. Refresh Administration automation for next turn
        9. Repair damaged fleets using available shipyards
        """
        from .models import Star, ProductionOrder
        self._micromanager_auto_fleet_ids_for_year = set()
        for star in Star.objects.filter(game=self.game, player__isnull=False):
            had_production_orders = star.production_orders.exists()
            star.buildpoints_consumed = 0
            colonists_busy = 0  # Track colonists busy with construction this turn
            construction_employment_base = calculate_total_jobs(star)
            available_bp = calculate_available_buildpoints(star)
            blocked = False
            fleets_built_this_turn = 0  # Track fleets built for shipyard availability
            shipyard_blocked_message_sent = False  # Only send once per star
            cost_map = get_player_production_costs(star.player)
            terraform_profile = get_player_terraforming_profile(star.player)
            terraform_rate = float(terraform_profile.get('rate', 0.0) or 0.0)

            # Track production counts for aggregate messages
            production_counts = {
                'mine': 0, 'factory': 0, 'lab': 0, 'defense': 0,
                'shipyard': 0, 'administration': 0, 'dyson_sphere': 0,
            }

            for order in list(star.production_orders.order_by('position')):
                if blocked:
                    break

                if (
                    order.added_by_micromanager and
                    not bool(getattr(star, 'has_administration', False))
                ):
                    order.delete()
                    continue

                if (
                    order.order_type == REMOVE_ADMINISTRATION_ORDER_TYPE and
                    not bool(getattr(star, 'has_administration', False))
                ):
                    order.delete()
                    continue
                if (
                    order.order_type == DYSON_SPHERE_ORDER_TYPE and
                    bool(getattr(star, 'has_dyson_sphere', False))
                ):
                    order.delete()
                    continue
                if (
                    order.order_type == DYSON_SPHERE_ORDER_TYPE and
                    (
                        int(getattr(order, 'quantity', 1) or 1) > 1 or
                        bool(getattr(order, 'repeat', False))
                    )
                ):
                    changed = []
                    if int(getattr(order, 'quantity', 1) or 1) > 1:
                        order.quantity = 1
                        changed.append('quantity')
                    if bool(getattr(order, 'repeat', False)):
                        order.repeat = False
                        changed.append('repeat')
                    if changed:
                        order.save(update_fields=changed)

                cost = cost_map.get(order.order_type, {})

                if order.order_type.startswith('TERRAFORM_') and terraform_rate <= 0:
                    blocked = True
                    order.save()
                    break

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
                    colonist_cost = int(cost.get('colonists', 0) or 0)

                    # Phase 1: Consume resources (must complete before labor)
                    for resource in ALL_RESOURCE_KEYS:
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
                        for resource in ALL_RESOURCE_KEYS
                    )

                    if not resources_satisfied:
                        # Blocked on resources - save and stop
                        blocked = True
                        order.save()
                        break

                    # Phase 2: Consume labor.
                    # Colonist-built mine/factory orders use spent_bp as their
                    # per-item labor progress tracker so they can carry partial
                    # progress across turns without needing a schema change.
                    bp_cost = int(cost.get('bp', 0) or 0)
                    labor_cost = colonist_cost if colonist_cost > 0 else bp_cost
                    labor_needed = labor_cost - order.spent_bp

                    if labor_needed > 0:
                        if colonist_cost > 0:
                            labor_spend = min(
                                labor_needed,
                                calculate_available_construction_colonists(
                                    star,
                                    colonists_busy=colonists_busy,
                                    employed_jobs=construction_employment_base,
                                ),
                            )
                        else:
                            labor_spend = min(labor_needed, available_bp)
                            available_bp -= labor_spend
                            star.buildpoints_consumed += labor_spend

                        order.spent_bp += labor_spend

                        if order.spent_bp < labor_cost:
                            # Blocked on labor - save and stop
                            blocked = True
                            order.save()
                            break

                    # Item complete! Mark colonists as busy for the rest of this turn.
                    if colonist_cost > 0:
                        colonists_busy += colonist_cost

                    self._apply_negative_production_refunds(star, cost)
                    fleet_built = self._apply_production_effect(
                        star,
                        order.order_type,
                        production_counts,
                        terraform_rate=terraform_rate,
                    )
                    if fleet_built:
                        fleets_built_this_turn += 1
                    order.completed += 1
                    # Reset spent amounts for next item
                    order.spent_ironium = 0
                    order.spent_boranium = 0
                    order.spent_germanium = 0
                    order.spent_resource_x = 0
                    order.spent_resource_y = 0
                    order.spent_resource_z = 0
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
            self._refresh_administration_production_queue(star)
            self._refresh_administration_fleet_dispatch_queue(star)
            self._send_production_orders_completed_message(star, had_production_orders)

            star.save()

            # Repair damaged fleets using available shipyards
            available_shipyards = star.shipyards - fleets_built_this_turn
            self._repair_fleets_at_star(star, available_shipyards)

    def _apply_production_effect(
        self, star, order_type, production_counts, terraform_rate=None
    ):
        """Apply the effect of a completed production order.

        Returns True if a fleet was built (for shipyard availability tracking).
        """
        if order_type == 'BUILD_FLEET':
            self._build_fleet(star)
            return True
        elif order_type == 'BUILD_MINE':
            self._build_mine(star)
            production_counts['mine'] += 1
        elif order_type == 'BUILD_FACTORY':
            self._build_factory(star)
            production_counts['factory'] += 1
        elif order_type == 'BUILD_COLONISTS_1K':
            self._build_colonists(star, 1000)
        elif order_type == 'BUILD_COLONISTS_1M':
            self._build_colonists(star, 1000000)
        elif order_type == 'BUILD_LAB':
            self._build_lab(star)
            production_counts['lab'] += 1
        elif order_type == 'BUILD_DEFENSE':
            self._build_defense(star)
            production_counts['defense'] += 1
        elif order_type == 'BUILD_SHIPYARD':
            self._build_shipyard(star)
            production_counts['shipyard'] += 1
        elif order_type == ADMINISTRATION_ORDER_TYPE:
            self._build_administration(star)
            production_counts['administration'] += 1
        elif order_type == REMOVE_ADMINISTRATION_ORDER_TYPE:
            self._remove_administration(star)
        elif order_type == DYSON_SPHERE_ORDER_TYPE:
            self._build_dyson_sphere(star)
            production_counts['dyson_sphere'] += 1
        elif str(order_type).startswith('TERRAFORM_'):
            self._apply_terraform_effect(
                star, order_type, terraform_rate=terraform_rate
            )
        return False

    def _build_fleet(self, star):
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
            warp_advantage=combine_speed_advantages(
                getattr(player.race_type, 'warp_advantage', 0.0) or 0.0,
                tech_effects.get('warp_advantage', 0.0) or 0.0,
            ),
            wormhole_fuel_per_ly=tech_effects.get('wormhole_fuel_per_ly', 5.0),
            wormhole_destruction_chance=tech_effects.get('wormhole_destruction_chance', 0.0),
            offense_level=tech_effects['offense_level'],
            defense_level=tech_effects['defense_level'],
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

    def _build_colonists(self, star, amount):
        """Add produced colonists to a mechanical colony."""
        star.colonists = int(star.colonists or 0) + int(amount or 0)

    def _build_lab(self, star):
        """Build a lab at the given star."""
        star.labs += 1

    def _build_defense(self, star):
        """Build a defense at the given star."""
        star.defenses += 1

    def _build_shipyard(self, star):
        """Build a shipyard at the given star."""
        star.shipyards += 1

    def _build_administration(self, star):
        """Build Administration at the given star."""
        star.has_administration = True

    def _remove_administration(self, star):
        """Remove Administration from the given star."""
        star.has_administration = False

    def _build_dyson_sphere(self, star):
        """Build a Dyson Sphere at the given star."""
        star.has_dyson_sphere = True

    def _apply_negative_production_refunds(self, star, cost):
        """Apply any negative production costs as inventory refunds."""
        for resource in ALL_RESOURCE_KEYS:
            refund = int(cost.get(resource, 0) or 0)
            if refund >= 0:
                continue
            inventory_field = '%s_inventory' % resource
            current = int(getattr(star, inventory_field, 0) or 0)
            setattr(star, inventory_field, current + abs(refund))

    def _send_production_summary_messages(self, star, production_counts):
        """Send one construction rollup message per star per year."""
        player = star.player
        completed = {
            key: int(production_counts.get(key) or 0)
            for key in (
                'mine', 'factory', 'lab', 'defense', 'shipyard',
                'administration', 'dyson_sphere',
            )
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

    def _apply_terraform_order(self, star, order, terraform_rate=None):
        """Apply a single terraforming order.

        Each turn moves a fraction of the remaining distance toward the player's ideal.
        This produces exponential decay that never quite reaches perfection.
        Modifies the environmental value directly.
        """
        rate = terraform_rate
        if rate is None:
            profile = get_player_terraforming_profile(star.player)
            rate = float(profile.get('rate', 0.0) or 0.0)
        multiplier = 1.0
        race_type = getattr(star.player, 'race_type', None)
        if race_type is not None:
            try:
                multiplier = float(
                    getattr(race_type, 'terraforming_multiplier', 1.0) or 1.0
                )
            except (TypeError, ValueError):
                multiplier = 1.0
        rate = max(0.0, float(rate or 0.0) * multiplier)
        if rate <= 0:
            return

        self._apply_terraform_effect(
            star, getattr(order, 'order_type', None), terraform_rate=rate
        )

    def _apply_terraform_effect(self, star, order_type, terraform_rate=None):
        """Apply a single terraforming effect by order type."""
        env_map = {
            'TERRAFORM_GRAVITY': ('gravity', star.player.gravity_center),
            'TERRAFORM_TEMPERATURE': (
                'temperature', star.player.temperature_center
            ),
            'TERRAFORM_RADIATION': ('radiation', star.player.radiation_center),
        }
        if order_type not in (
            'TERRAFORM_GRAVITY',
            'TERRAFORM_TEMPERATURE',
            'TERRAFORM_RADIATION',
        ):
            return
        rate = terraform_rate
        if rate is None:
            profile = get_player_terraforming_profile(star.player)
            rate = float(profile.get('rate', 0.0) or 0.0)
        if rate <= 0:
            return

        field, target = env_map[order_type]
        current = getattr(star, field)

        # Move a portion of the way from current to target
        distance = target - current
        new_value = current + distance * rate

        # Clamp to valid range
        new_value = max(0.0, min(2.0, new_value))

        setattr(star, field, new_value)
        star.save()

    def _order_has_progress(self, order):
        if int(getattr(order, 'completed', 0) or 0) > 0:
            return True
        if int(getattr(order, 'spent_bp', 0) or 0) > 0:
            return True
        for key in ALL_RESOURCE_KEYS:
            if int(getattr(order, 'spent_%s' % key, 0) or 0) > 0:
                return True
        return False

    def _resequence_production_orders(self, star):
        """Ensure player orders are before Micromanager orders."""
        orders = list(star.production_orders.order_by(
            'added_by_micromanager', 'position', 'id'
        ))
        changed = []
        for idx, order in enumerate(orders, start=1):
            if int(order.position or 0) == idx:
                continue
            order.position = idx
            changed.append(order)
        for order in changed:
            order.save(update_fields=['position'])

    def _projected_player_economy_order_types(self, orders):
        """Return remaining player mine/factory orders as projected types."""
        projected = []
        for order in list(orders or []):
            if bool(getattr(order, 'added_by_micromanager', False)):
                continue
            if getattr(order, 'order_type', None) not in (
                'BUILD_MINE',
                'BUILD_FACTORY',
            ):
                continue
            remaining = max(
                0,
                int(getattr(order, 'quantity', 0) or 0) -
                int(getattr(order, 'completed', 0) or 0),
            )
            if remaining <= 0:
                continue
            projected.extend([order.order_type] * remaining)
        return projected

    def _convert_repeat_player_infrastructure_orders_to_micromanager(
        self,
        star,
        tier,
    ):
        """Hand repeat infrastructure orders to tier-2+ Administration."""
        managed_types = set(get_micromanager_managed_order_types(tier))
        if (
            int(tier or 0) < 2 or
            not managed_types
        ):
            return

        for order in star.production_orders.filter(
            added_by_micromanager=False,
            repeat=True,
        ).order_by('position', 'id'):
            if order.order_type not in managed_types:
                continue
            if self._order_has_progress(order):
                continue
            order.added_by_micromanager = True
            order.repeat = False
            order.save(update_fields=['added_by_micromanager', 'repeat'])

    def _refresh_administration_production_queue(self, star):
        """Refresh zero-progress Micromanager queue items for one colony."""
        from .models import ProductionOrder

        profile = get_player_administration_profile(star.player)
        tier = int(profile.get('level', 0) or 0)
        ai_tier = int(player_ai_administration_tier(star.player) or 0)
        if ai_tier > tier:
            tier = ai_tier
        admin_active = bool(getattr(star, 'has_administration', False) or ai_tier > 0)
        micromanager_orders = list(star.production_orders.filter(
            added_by_micromanager=True
        ).order_by('position', 'id'))

        if tier <= 0 or not admin_active:
            for order in micromanager_orders:
                if self._order_has_progress(order):
                    continue
                order.delete()
            self._resequence_production_orders(star)
            return

        self._convert_repeat_player_infrastructure_orders_to_micromanager(
            star,
            tier,
        )
        micromanager_orders = list(star.production_orders.filter(
            added_by_micromanager=True
        ).order_by('position', 'id'))

        preserved = []
        editable = []
        for order in micromanager_orders:
            if self._order_has_progress(order):
                preserved.append(order)
                continue
            editable.append(order)

        self._resequence_production_orders(star)

        existing_types = []
        for order in preserved:
            remaining = max(
                0,
                int(getattr(order, 'quantity', 0) or 0) -
                int(getattr(order, 'completed', 0) or 0),
            )
            for _ in range(remaining):
                existing_types.append(order.order_type)
        terraform_profile = get_player_terraforming_profile(star.player)
        terraform_rate = float(terraform_profile.get('rate', 0.0) or 0.0)
        dyson_profile = get_player_dyson_sphere_profile(star.player)
        queue_orders = list(star.production_orders.exclude(
            id__in=[order.id for order in editable]
        ))
        player_projected_types = self._projected_player_economy_order_types(
            queue_orders
        )
        cost_map = get_player_production_costs(star.player)
        planned = plan_micromanager_orders(
            star.player,
            star,
            tier,
            fleets_in_orbit=star.player.fleets.filter(x=star.x, y=star.y).count(),
            terraform_available=(terraform_rate > 0),
            terraform_rate=terraform_rate,
            dyson_available=bool(dyson_profile.get('unlocked')),
            preplanned_orders=existing_types + player_projected_types,
            cost_map=cost_map,
            queue_requirements=remaining_queue_requirements(
                queue_orders, cost_map
            ),
        )
        planned_runs = collapse_micromanager_order_totals(planned)
        if preserved and planned_runs:
            preserved_by_type = {}
            for order in preserved:
                if order.order_type not in preserved_by_type:
                    preserved_by_type[order.order_type] = order
            remaining_runs = []
            for order_type, quantity in planned_runs:
                preserved_order = preserved_by_type.get(order_type)
                if preserved_order is None:
                    remaining_runs.append((order_type, quantity))
                    continue
                preserved_order.quantity = (
                    int(preserved_order.quantity or 0) +
                    int(quantity or 0)
                )
                preserved_order.save(update_fields=['quantity'])
            planned_runs = remaining_runs

        tail_base = star.production_orders.exclude(
            id__in=[order.id for order in editable]
        ).aggregate(
            max_pos=models.Max('position')
        )['max_pos'] or 0
        for idx, run in enumerate(planned_runs):
            order_type, quantity = run
            position = tail_base + idx + 1
            if idx < len(editable):
                order = editable[idx]
                changed = []
                if order.order_type != order_type:
                    order.order_type = order_type
                    changed.append('order_type')
                if int(order.quantity or 0) != int(quantity):
                    order.quantity = quantity
                    changed.append('quantity')
                if int(order.position or 0) != int(position):
                    order.position = position
                    changed.append('position')
                if not changed:
                    continue
                order.save(update_fields=changed)
                continue
            ProductionOrder.objects.create(
                game=self.game,
                star=star,
                order_type=order_type,
                position=position,
                quantity=quantity,
                repeat=False,
                added_by_micromanager=True,
            )

        for order in editable[len(planned_runs):]:
            order.delete()

    @staticmethod
    def _resource_inventory_map(obj):
        return {
            key: int(getattr(obj, '%s_inventory' % key, 0) or 0)
            for key in ALL_RESOURCE_KEYS
        }

    @staticmethod
    def _distance_between_points(x1, y1, x2, y2):
        dx = float(int(x1) - int(x2))
        dy = float(int(y1) - int(y2))
        return sqrt((dx * dx) + (dy * dy))

    def _resource_deficits_for_star(self, star, cost_map):
        """Return mineral deficits against one-year queue + projected output."""
        queue_orders = list(star.production_orders.all())
        queue_requirements = remaining_queue_requirements(queue_orders, cost_map)
        projected_output = projected_mining_output(star)
        deficits = {}
        for key in ALL_RESOURCE_KEYS:
            available = (
                int(getattr(star, '%s_inventory' % key, 0) or 0) +
                int(projected_output.get(key, 0) or 0)
            )
            required = int(queue_requirements.get(key, 0) or 0)
            deficits[key] = max(0, required - available)
        return deficits

    def _resource_surplus_for_star(self, star, cost_map, reserve_factor=1):
        """Return mineral surplus after keeping queue reserves on colony."""
        queue_orders = list(star.production_orders.all())
        queue_requirements = remaining_queue_requirements(queue_orders, cost_map)
        reserve_factor = max(1, int(reserve_factor or 1))
        surplus = {}
        for key in ALL_RESOURCE_KEYS:
            reserve = int(queue_requirements.get(key, 0) or 0) * reserve_factor
            stock = int(getattr(star, '%s_inventory' % key, 0) or 0)
            surplus[key] = max(0, stock - reserve)
        return surplus

    @staticmethod
    def _fleet_defense_score(fleet):
        """Score a fleet for colony defense retention."""
        offense = float(getattr(fleet, 'offense_level', 0.0) or 0.0)
        defense = float(getattr(fleet, 'defense_level', 0.0) or 0.0)
        ships = int(getattr(fleet, 'ship_count', 0) or 0)
        return (offense + defense, ships)

    def _dispatchable_idle_fleets_for_colony(self, orbit_fleets, idle_fleets):
        """Return weakest idle fleets that can be sent without stripping defense."""
        orbit = list(orbit_fleets or [])
        idle = list(idle_fleets or [])
        if not orbit or not idle:
            return []
        if len(orbit) <= 1:
            return []

        ranked = sorted(
            orbit,
            key=lambda fleet: (
                self._fleet_defense_score(fleet)[0],
                self._fleet_defense_score(fleet)[1],
                int(fleet.id or 0),
            ),
            reverse=True,
        )
        reserve_fleet_count = max(
            1,
            int(ceil(float(len(ranked)) * MICROMANAGER_DEFENSE_FLEET_RATIO)),
        )
        total_ships = sum(int(getattr(fleet, 'ship_count', 0) or 0) for fleet in ranked)
        reserve_ship_count = max(
            1,
            int(ceil(float(total_ships) * MICROMANAGER_DEFENSE_SHIP_RATIO)),
        )

        reserved_ids = set()
        reserved_ships = 0
        for fleet in ranked:
            if (
                len(reserved_ids) >= reserve_fleet_count and
                reserved_ships >= reserve_ship_count
            ):
                break
            reserved_ids.add(fleet.id)
            reserved_ships += int(getattr(fleet, 'ship_count', 0) or 0)

        dispatchable = [
            fleet for fleet in idle
            if fleet.id not in reserved_ids
        ]
        dispatchable.sort(
            key=lambda fleet: (
                self._fleet_defense_score(fleet)[0],
                self._fleet_defense_score(fleet)[1],
                int(fleet.id or 0),
            )
        )
        return dispatchable

    def _transfer_amounts_for_need_and_supply(self, demand, supply, capacity):
        """Allocate transfer amounts by demand priority, bounded by capacity."""
        remaining = max(0, int(capacity or 0))
        if remaining <= 0:
            return {key: 0 for key in ALL_RESOURCE_KEYS}
        demand = demand or {}
        supply = supply or {}
        priorities = sorted(
            ALL_RESOURCE_KEYS,
            key=lambda key: (int(demand.get(key, 0) or 0), key),
            reverse=True,
        )
        transfers = {key: 0 for key in ALL_RESOURCE_KEYS}
        for key in priorities:
            if remaining <= 0:
                break
            needed = max(0, int(demand.get(key, 0) or 0))
            available = max(0, int(supply.get(key, 0) or 0))
            if needed <= 0 or available <= 0:
                continue
            amount = min(remaining, needed, available)
            transfers[key] = amount
            remaining -= amount
        return transfers

    @staticmethod
    def _total_transfer_amount(transfers):
        if not transfers:
            return 0
        return sum(max(0, int(transfers.get(key, 0) or 0)) for key in ALL_RESOURCE_KEYS)

    def _one_year_planning_budget(self, star, cost_map):
        """Return one-year budget after queued demand for horizon planning."""
        queue_orders = list(star.production_orders.all())
        queue_requirements = remaining_queue_requirements(queue_orders, cost_map)
        mining_output = projected_mining_output(star)
        budget = {
            'bp': max(
                0,
                int(calculate_available_buildpoints(star) or 0) -
                int(queue_requirements.get('bp', 0) or 0),
            ),
        }
        for key in ALL_RESOURCE_KEYS:
            available = (
                int(getattr(star, '%s_inventory' % key, 0) or 0) +
                int(mining_output.get(key, 0) or 0) -
                int(queue_requirements.get(key, 0) or 0)
            )
            budget[key] = max(0, int(available))
        return budget

    @staticmethod
    def _one_year_income(star):
        income = {'bp': max(0, int(calculate_available_buildpoints(star) or 0))}
        mining_output = projected_mining_output(star)
        for key in ALL_RESOURCE_KEYS:
            income[key] = max(0, int(mining_output.get(key, 0) or 0))
        return income

    @staticmethod
    def _order_can_complete_within_years(cost_map, order_type, budget, income, years):
        """Return True when an order can complete within the given horizon."""
        if not cost_map:
            return False
        cost = cost_map.get(order_type, {})
        if not isinstance(cost, dict):
            return False
        years = max(1, int(years or 1))
        horizon_extra_years = max(0, years - 1)
        available_bp = (
            max(0, int(budget.get('bp', 0) or 0)) +
            max(0, int(income.get('bp', 0) or 0)) * horizon_extra_years
        )
        if max(0, int(cost.get('bp', 0) or 0)) > available_bp:
            return False
        for key in ALL_RESOURCE_KEYS:
            available = (
                max(0, int(budget.get(key, 0) or 0)) +
                max(0, int(income.get(key, 0) or 0)) * horizon_extra_years
            )
            if max(0, int(cost.get(key, 0) or 0)) > available:
                return False
        return True

    def _queue_auto_build_fleet_order_for_colony(self, star, orbit_fleets, cost_map):
        """Tier-5: queue one auto build-fleet order when below orbit target."""
        from .models import ProductionOrder

        orbit_count = len(list(orbit_fleets or []))
        if orbit_count >= MICROMANAGER_MAX_ORBIT_FLEETS:
            return
        if int(getattr(star, 'shipyards', 0) or 0) <= 0:
            return
        if star.production_orders.filter(order_type='BUILD_FLEET').exists():
            return
        budget = self._one_year_planning_budget(star, cost_map)
        income = self._one_year_income(star)
        if not self._order_can_complete_within_years(
            cost_map,
            'BUILD_FLEET',
            budget,
            income,
            MICROMANAGER_FLEET_BUILD_MAX_YEARS,
        ):
            return
        tail_base = star.production_orders.aggregate(
            max_pos=models.Max('position')
        )['max_pos'] or 0
        ProductionOrder.objects.create(
            game=self.game,
            star=star,
            order_type='BUILD_FLEET',
            position=int(tail_base) + 1,
            quantity=1,
            repeat=False,
            added_by_micromanager=True,
        )

    def _best_colony_source_for_deficits(self, star, deficits, fleet, cost_map):
        """Pick best same-owner colony source for this colony's deficits."""
        player = getattr(star, 'player', None)
        if not player:
            return None, None
        capacity = int(getattr(fleet, 'cargo_remaining', 0) or 0)
        if capacity <= 0:
            return None, None

        best_source = None
        best_transfer = None
        best_score = 0
        best_distance = None
        for source in player.stars.exclude(id=star.id):
            if source.player_id != player.id:
                continue
            if int(getattr(source, 'colonists', 0) or 0) <= 0:
                continue
            surplus = self._resource_surplus_for_star(
                source, cost_map, reserve_factor=1
            )
            transfers = self._transfer_amounts_for_need_and_supply(
                deficits, surplus, capacity
            )
            score = self._total_transfer_amount(transfers)
            if score <= 0:
                continue
            distance = self._distance_between_points(star.x, star.y, source.x, source.y)
            if (
                best_source is None or
                score > best_score or
                (score == best_score and (best_distance is None or distance < best_distance))
            ):
                best_source = source
                best_transfer = transfers
                best_score = score
                best_distance = distance
        return best_source, best_transfer

    def _best_asteroid_source_for_deficits(self, star, deficits, fleet):
        """Pick best nearby asteroid field source for unmet deficits."""
        from .models import Salvage

        capacity = int(getattr(fleet, 'cargo_remaining', 0) or 0)
        if capacity <= 0:
            return None, None

        min_x = int(star.x) - int(ceil(MICROMANAGER_ASTEROID_SEARCH_RADIUS))
        max_x = int(star.x) + int(ceil(MICROMANAGER_ASTEROID_SEARCH_RADIUS))
        min_y = int(star.y) - int(ceil(MICROMANAGER_ASTEROID_SEARCH_RADIUS))
        max_y = int(star.y) + int(ceil(MICROMANAGER_ASTEROID_SEARCH_RADIUS))
        candidates = Salvage.objects.filter(
            game=self.game,
            salvage_type=Salvage.TYPE_ASTEROID_FIELD,
            x__gte=min_x,
            x__lte=max_x,
            y__gte=min_y,
            y__lte=max_y,
        )

        best_salvage = None
        best_transfer = None
        best_score = 0
        best_distance = None
        for salvage in candidates:
            distance = self._distance_between_points(star.x, star.y, salvage.x, salvage.y)
            if distance > MICROMANAGER_ASTEROID_SEARCH_RADIUS:
                continue
            supply = self._resource_inventory_map(salvage)
            transfers = self._transfer_amounts_for_need_and_supply(
                deficits, supply, capacity
            )
            score = self._total_transfer_amount(transfers)
            if score <= 0:
                continue
            if (
                best_salvage is None or
                score > best_score or
                (score == best_score and (best_distance is None or distance < best_distance))
            ):
                best_salvage = salvage
                best_transfer = transfers
                best_score = score
                best_distance = distance
        return best_salvage, best_transfer

    def _best_colony_destination_for_excess(self, source_star, excess, fleet, cost_map):
        """Pick best colony destination for optional excess redistribution."""
        player = getattr(source_star, 'player', None)
        if not player:
            return None, None
        capacity = int(getattr(fleet, 'cargo_remaining', 0) or 0)
        if capacity <= 0:
            return None, None

        best_dest = None
        best_transfer = None
        best_score = 0
        best_distance = None
        for dest in player.stars.exclude(id=source_star.id):
            if dest.player_id != player.id:
                continue
            if int(getattr(dest, 'colonists', 0) or 0) <= 0:
                continue
            deficits = self._resource_deficits_for_star(dest, cost_map)
            transfers = self._transfer_amounts_for_need_and_supply(
                deficits, excess, capacity
            )
            score = self._total_transfer_amount(transfers)
            if score <= 0:
                continue
            distance = self._distance_between_points(
                source_star.x, source_star.y, dest.x, dest.y
            )
            if (
                best_dest is None or
                score > best_score or
                (score == best_score and (best_distance is None or distance < best_distance))
            ):
                best_dest = dest
                best_transfer = transfers
                best_score = score
                best_distance = distance
        return best_dest, best_transfer

    def _create_auto_move_order(self, fleet, position, target_star=None, target_salvage=None):
        from .models import FleetOrders

        try:
            move_warp = int(getattr(fleet, 'max_safe_warp', 5) or 5)
        except (TypeError, ValueError):
            move_warp = 5
        move_warp = max(1, min(13, move_warp))

        kwargs = {
            'game': self.game,
            'fleet': fleet,
            'position': int(position),
            'order_type': 'MOVE',
            'repeat': False,
            'warpfactor': move_warp,
            'original_warpfactor': move_warp,
            'overmax_risk_checked': False,
            'added_by_micromanager': True,
        }
        if target_star is not None:
            kwargs.update({
                'target_star': target_star,
                'target_kind': 'OBJECT',
                'target_short_id': target_star.short_id,
                'x': int(target_star.x),
                'y': int(target_star.y),
            })
        elif target_salvage is not None:
            kwargs.update({
                'target_salvage': target_salvage,
                'target_kind': 'OBJECT',
                'target_short_id': target_salvage.short_id,
                'x': int(target_salvage.x),
                'y': int(target_salvage.y),
            })
        FleetOrders.objects.create(**kwargs)

    def _create_auto_transfer_order(
        self,
        fleet,
        position,
        transfer_type,
        transfers,
        target_star=None,
        target_salvage=None,
        transfer_colonists=0,
    ):
        from .models import FleetOrders

        kwargs = {
            'game': self.game,
            'fleet': fleet,
            'position': int(position),
            'order_type': 'TRANSFER',
            'repeat': False,
            'transfer_type': transfer_type,
            'transfer_ironium': int(transfers.get('ironium', 0) or 0),
            'transfer_boranium': int(transfers.get('boranium', 0) or 0),
            'transfer_germanium': int(transfers.get('germanium', 0) or 0),
            'transfer_resource_x': int(transfers.get('resource_x', 0) or 0),
            'transfer_resource_y': int(transfers.get('resource_y', 0) or 0),
            'transfer_resource_z': int(transfers.get('resource_z', 0) or 0),
            'transfer_colonists': max(0, int(transfer_colonists or 0)),
            'added_by_micromanager': True,
        }
        if target_star is not None:
            kwargs.update({
                'target_star': target_star,
                'target_kind': 'OBJECT',
                'target_short_id': target_star.short_id,
                'x': int(target_star.x),
                'y': int(target_star.y),
            })
        elif target_salvage is not None:
            kwargs.update({
                'target_salvage': target_salvage,
                'target_kind': 'OBJECT',
                'target_short_id': target_salvage.short_id,
                'x': int(target_salvage.x),
                'y': int(target_salvage.y),
            })
        FleetOrders.objects.create(**kwargs)

    def _queue_auto_collect_route(
        self,
        fleet,
        home_star,
        transfers,
        pickup_star=None,
        pickup_salvage=None,
    ):
        """Queue a collect route: travel, load, return, unload."""
        total = self._total_transfer_amount(transfers)
        if total <= 0:
            return False
        pickup_x = int(pickup_star.x if pickup_star is not None else pickup_salvage.x)
        pickup_y = int(pickup_star.y if pickup_star is not None else pickup_salvage.y)
        same_pickup = int(fleet.x) == pickup_x and int(fleet.y) == pickup_y

        start_position = (
            fleet.orders.aggregate(max_pos=models.Max('position'))['max_pos'] or 0
        )
        position = int(start_position) + 1
        if not same_pickup:
            self._create_auto_move_order(
                fleet,
                position,
                target_star=pickup_star,
                target_salvage=pickup_salvage,
            )
            position += 1
        self._create_auto_transfer_order(
            fleet,
            position,
            'LOAD',
            transfers,
            target_star=pickup_star,
            target_salvage=pickup_salvage,
        )
        position += 1
        self._create_auto_move_order(
            fleet,
            position,
            target_star=home_star,
        )
        position += 1
        self._create_auto_transfer_order(
            fleet,
            position,
            'UNLOAD',
            transfers,
            target_star=home_star,
        )
        return True

    def _queue_auto_delivery_route(self, fleet, source_star, dest_star, transfers):
        """Queue an excess delivery route and return fleet to source colony."""
        total = self._total_transfer_amount(transfers)
        if total <= 0:
            return False

        start_position = (
            fleet.orders.aggregate(max_pos=models.Max('position'))['max_pos'] or 0
        )
        position = int(start_position) + 1
        self._create_auto_transfer_order(
            fleet,
            position,
            'LOAD',
            transfers,
            target_star=source_star,
        )
        position += 1
        self._create_auto_move_order(
            fleet,
            position,
            target_star=dest_star,
        )
        position += 1
        self._create_auto_transfer_order(
            fleet,
            position,
            'UNLOAD',
            transfers,
            target_star=dest_star,
        )
        position += 1
        self._create_auto_move_order(
            fleet,
            position,
            target_star=source_star,
        )
        return True

    def _create_auto_colonise_order(self, fleet, position, target_star):
        from .models import FleetOrders

        try:
            warp = int(getattr(fleet, 'max_safe_warp', 5) or 5)
        except (TypeError, ValueError):
            warp = 5
        warp = max(1, min(13, warp))
        FleetOrders.objects.create(
            game=self.game,
            fleet=fleet,
            position=int(position),
            order_type='COLONISE',
            repeat=False,
            warpfactor=warp,
            original_warpfactor=warp,
            overmax_risk_checked=False,
            target_star=target_star,
            target_kind='OBJECT',
            target_short_id=target_star.short_id,
            x=int(target_star.x),
            y=int(target_star.y),
            added_by_micromanager=True,
        )

    def _queue_auto_colonise_route(
        self,
        fleet,
        source_star,
        target_star,
        colonists_kt,
    ):
        """Queue load -> move -> colonise for one fleet."""
        transfer_amount = max(0, int(colonists_kt or 0))
        if transfer_amount <= 0:
            return False
        start_position = (
            fleet.orders.aggregate(max_pos=models.Max('position'))['max_pos'] or 0
        )
        position = int(start_position) + 1
        self._create_auto_transfer_order(
            fleet,
            position,
            'LOAD',
            {},
            target_star=source_star,
            transfer_colonists=transfer_amount,
        )
        position += 1
        if int(fleet.x) != int(target_star.x) or int(fleet.y) != int(target_star.y):
            self._create_auto_move_order(
                fleet,
                position,
                target_star=target_star,
            )
            position += 1
        self._create_auto_colonise_order(
            fleet,
            position,
            target_star,
        )
        return True

    def _idle_orbit_fleets(self, orbit_fleets):
        idle = []
        for fleet in list(orbit_fleets or []):
            if fleet.id in self._micromanager_auto_fleet_ids_for_year:
                continue
            if fleet.orders.exists():
                continue
            idle.append(fleet)
        return idle

    def _spare_colonists_for_auto_colonise(self, star):
        """Return spare colony colonists in kt while preserving local workforce."""
        current_colonists = max(0, int(getattr(star, 'colonists', 0) or 0))
        reserve_colonists = max(
            int(getattr(star, 'base_capacity', 0) or 0),
            int(calculate_total_jobs(star) or 0) * 2,
            int(MICROMANAGER_COLONISE_RESERVE_COLONISTS or 0) * 1000,
        )
        return max(0, int((current_colonists - reserve_colonists) / 1000))

    def _best_colonise_target_for_colony(self, star):
        from .models import Star

        player = getattr(star, 'player', None)
        if player is None:
            return None
        min_x = int(star.x) - int(ceil(MICROMANAGER_COLONISE_SEARCH_RADIUS))
        max_x = int(star.x) + int(ceil(MICROMANAGER_COLONISE_SEARCH_RADIUS))
        min_y = int(star.y) - int(ceil(MICROMANAGER_COLONISE_SEARCH_RADIUS))
        max_y = int(star.y) + int(ceil(MICROMANAGER_COLONISE_SEARCH_RADIUS))
        best = None
        best_distance = None
        best_hab = None
        for target in Star.objects.filter(
            game=self.game,
            player__isnull=True,
            x__gte=min_x,
            x__lte=max_x,
            y__gte=min_y,
            y__lte=max_y,
        ).exclude(id=star.id):
            distance = self._distance_between_points(
                star.x, star.y, target.x, target.y
            )
            if distance > MICROMANAGER_COLONISE_SEARCH_RADIUS:
                continue
            hab = float(calculate_habitability_factor(player, target) or 0.0)
            if hab <= 0.0:
                continue
            if (
                best is None or
                hab > best_hab or
                (hab == best_hab and (best_distance is None or distance < best_distance))
            ):
                best = target
                best_hab = hab
                best_distance = distance
        return best

    def _dispatch_auto_colonise_route(self, star, orbit_fleets):
        """Tier-5: dispatch one idle fleet to colonise a nearby viable star."""
        idle_fleets = self._idle_orbit_fleets(orbit_fleets)
        dispatchable = self._dispatchable_idle_fleets_for_colony(
            orbit_fleets, idle_fleets
        )
        if not dispatchable:
            return
        target_star = self._best_colonise_target_for_colony(star)
        if target_star is None:
            return
        spare_colonists = self._spare_colonists_for_auto_colonise(star)
        if spare_colonists <= 0:
            return

        dispatches = 0
        for fleet in dispatchable:
            if dispatches >= MICROMANAGER_COLONISE_DISPATCHES_PER_COLONY:
                break
            cargo_remaining = int(getattr(fleet, 'cargo_remaining', 0) or 0)
            if cargo_remaining <= 0:
                continue
            transfer_colonists = min(
                spare_colonists,
                cargo_remaining,
            )
            transfer_colonists = max(
                0,
                int(transfer_colonists or 0),
            )
            if transfer_colonists < MICROMANAGER_COLONISE_MIN_PAYLOAD:
                continue
            created = self._queue_auto_colonise_route(
                fleet,
                source_star=star,
                target_star=target_star,
                colonists_kt=transfer_colonists,
            )
            if not created:
                continue
            self._micromanager_auto_fleet_ids_for_year.add(fleet.id)
            dispatches += 1
            spare_colonists = max(0, spare_colonists - transfer_colonists)
            if spare_colonists < MICROMANAGER_COLONISE_MIN_PAYLOAD:
                break

    def _count_colony_patrol_fleets(self, orbit_fleets):
        count = 0
        for fleet in list(orbit_fleets or []):
            if fleet.orders.filter(order_type='PATROL').exists():
                count += 1
        return count

    def _assign_auto_patrol_orders(self, star, orbit_fleets):
        """Tier-5: assign repeat patrol orders to idle orbit fleets."""
        idle_fleets = self._idle_orbit_fleets(orbit_fleets)
        if not idle_fleets:
            return
        patrol_fleets_now = self._count_colony_patrol_fleets(orbit_fleets)
        patrol_target = int(
            ceil(float(len(orbit_fleets or [])) * MICROMANAGER_PATROL_IDLE_RATIO)
        )
        if patrol_target <= 0 and len(orbit_fleets or []) > 0:
            patrol_target = 1
        patrol_target = max(1, patrol_target)
        needed = max(0, patrol_target - patrol_fleets_now)
        if needed <= 0:
            return

        ranked_idle = sorted(
            idle_fleets,
            key=lambda fleet: (
                self._fleet_defense_score(fleet)[0],
                self._fleet_defense_score(fleet)[1],
                int(fleet.id or 0),
            ),
            reverse=True,
        )
        from .models import FleetOrders
        for fleet in ranked_idle:
            if needed <= 0:
                break
            try:
                intercept_speed = int(getattr(fleet, 'max_safe_warp', 5) or 5)
            except (TypeError, ValueError):
                intercept_speed = 5
            intercept_speed = max(1, min(13, intercept_speed))
            FleetOrders.objects.create(
                game=self.game,
                fleet=fleet,
                order_type='PATROL',
                repeat=True,
                patrol_radius=MICROMANAGER_PATROL_RADIUS,
                intercept_speed=intercept_speed,
                x=int(star.x),
                y=int(star.y),
                target_kind='SPACE',
                target_short_id=None,
                added_by_micromanager=True,
            )
            self._micromanager_auto_fleet_ids_for_year.add(fleet.id)
            needed -= 1

    def _refresh_administration_fleet_dispatch_queue(self, star):
        """Tier-4 Administration: auto-dispatch idle fleets for logistics."""
        from .models import Fleet

        player = getattr(star, 'player', None)
        if not player:
            return
        profile = get_player_administration_profile(player)
        tier = int(profile.get('level', 0) or 0)
        ai_tier = int(player_ai_administration_tier(player) or 0)
        if ai_tier > tier:
            tier = ai_tier
        if not bool(getattr(star, 'has_administration', False)) and ai_tier <= 0:
            return
        if tier < MICROMANAGER_FLEET_TIER:
            return

        cost_map = get_player_production_costs(player)
        if not hasattr(self, '_micromanager_auto_fleet_ids_for_year'):
            self._micromanager_auto_fleet_ids_for_year = set()

        orbit_fleets = list(Fleet.objects.filter(
            game=self.game,
            player=player,
            x=star.x,
            y=star.y,
        ).order_by('id'))
        if int(tier or 0) >= MICROMANAGER_ADVANCED_FLEET_TIER:
            self._queue_auto_build_fleet_order_for_colony(
                star,
                orbit_fleets,
                cost_map,
            )

        idle_fleets = self._idle_orbit_fleets(orbit_fleets)
        dispatchable_fleets = self._dispatchable_idle_fleets_for_colony(
            orbit_fleets, idle_fleets
        )
        if dispatchable_fleets:
            deficits = self._resource_deficits_for_star(star, cost_map)
            dispatches = 0
            for fleet in dispatchable_fleets:
                if dispatches >= MICROMANAGER_FLEET_DISPATCHES_PER_COLONY:
                    break
                if int(getattr(fleet, 'cargo_remaining', 0) or 0) <= 0:
                    continue

                created = False
                delivered = {key: 0 for key in ALL_RESOURCE_KEYS}
                if self._total_transfer_amount(deficits) > 0:
                    source_star, transfers = self._best_colony_source_for_deficits(
                        star, deficits, fleet, cost_map
                    )
                    if source_star and self._total_transfer_amount(transfers) > 0:
                        created = self._queue_auto_collect_route(
                            fleet,
                            home_star=star,
                            transfers=transfers,
                            pickup_star=source_star,
                        )
                        if created:
                            delivered = transfers
                    else:
                        source_salvage, transfers = self._best_asteroid_source_for_deficits(
                            star, deficits, fleet
                        )
                        if source_salvage and self._total_transfer_amount(transfers) > 0:
                            created = self._queue_auto_collect_route(
                                fleet,
                                home_star=star,
                                transfers=transfers,
                                pickup_salvage=source_salvage,
                            )
                            if created:
                                delivered = transfers
                else:
                    excess = self._resource_surplus_for_star(
                        star, cost_map, reserve_factor=2
                    )
                    target_star, transfers = self._best_colony_destination_for_excess(
                        star, excess, fleet, cost_map
                    )
                    if target_star and self._total_transfer_amount(transfers) > 0:
                        created = self._queue_auto_delivery_route(
                            fleet,
                            source_star=star,
                            dest_star=target_star,
                            transfers=transfers,
                        )

                if not created:
                    continue

                self._micromanager_auto_fleet_ids_for_year.add(fleet.id)
                dispatches += 1
                for key in ALL_RESOURCE_KEYS:
                    deficits[key] = max(
                        0,
                        int(deficits.get(key, 0) or 0) -
                        int(delivered.get(key, 0) or 0),
                    )

        if int(tier or 0) >= MICROMANAGER_ADVANCED_FLEET_TIER:
            self._dispatch_auto_colonise_route(star, orbit_fleets)
            self._assign_auto_patrol_orders(star, orbit_fleets)

    def _fleet_service_requirements(self, fleet):
        """Return per-fleet service demand in shipyard-units (repair/refuel)."""
        ship_count = max(1, int(getattr(fleet, 'ship_count', 1) or 1))
        integrity = int(getattr(fleet, 'integrity', 0) or 0)
        missing_integrity_pct = max(0, 100 - integrity)
        repair_units_needed = (float(missing_integrity_pct) * float(ship_count)) / 100.0

        max_fuel = float(getattr(fleet, 'max_fuel', 0.0) or 0.0)
        fuel = float(getattr(fleet, 'fuel', 0.0) or 0.0)
        if max_fuel <= 0.0:
            fuel_missing = 0.0
            refuel_units_needed = 0.0
        else:
            fuel_missing = max(0.0, max_fuel - fuel)
            refuel_units_needed = (
                (fuel_missing / max_fuel) * float(ship_count) if fuel_missing > 0.0 else 0.0
            )

        service_units_needed = max(repair_units_needed, refuel_units_needed)
        return {
            'ship_count': ship_count,
            'missing_integrity_pct': missing_integrity_pct,
            'repair_units_needed': repair_units_needed,
            'fuel': fuel,
            'max_fuel': max_fuel,
            'fuel_missing': fuel_missing,
            'refuel_units_needed': refuel_units_needed,
            'service_units_needed': service_units_needed,
        }

    def _service_fleet_with_shipyards(
        self,
        fleet,
        remaining_shipyards,
        service_rate,
        star,
    ):
        """Apply shipyard repair/refuel service to one fleet and return remaining pool."""
        if remaining_shipyards <= 0:
            return 0.0
        if not fleet or fleet.player is None:
            return remaining_shipyards
        try:
            rate = max(0.0, float(service_rate))
        except (TypeError, ValueError):
            rate = 0.0
        if rate <= 0.0:
            return remaining_shipyards

        req = self._fleet_service_requirements(fleet)
        service_units_needed = float(req['service_units_needed'])
        if service_units_needed <= 0.0:
            return remaining_shipyards

        max_service_units = float(remaining_shipyards) * rate
        service_units = min(service_units_needed, max_service_units)
        if service_units <= 0.0:
            return remaining_shipyards

        service_fraction = max(0.0, min(1.0, service_units / service_units_needed))
        old_integrity = int(fleet.integrity or 0)
        if req['missing_integrity_pct'] > 0:
            integrity_gain = int(float(req['missing_integrity_pct']) * service_fraction)
            if integrity_gain <= 0 and service_fraction > 0.0:
                integrity_gain = 1
            integrity_gain = min(int(req['missing_integrity_pct']), integrity_gain)
            fleet.integrity = min(100, old_integrity + integrity_gain)

        old_fuel = float(fleet.fuel or 0.0)
        if req['fuel_missing'] > 0.0:
            fuel_gain = float(req['fuel_missing']) * service_fraction
            if fuel_gain > 0.0:
                fleet.fuel = min(
                    float(req['max_fuel']),
                    old_fuel + fuel_gain,
                )

        update_fields = []
        if int(fleet.integrity or 0) != old_integrity:
            update_fields.append('integrity')
        if float(fleet.fuel or 0.0) != old_fuel:
            update_fields.append('fuel')
        if update_fields:
            fleet.save(update_fields=update_fields)

        if int(fleet.integrity or 0) > old_integrity:
            factory = FleetRepairedMessageFactory(
                self.game, fleet.player, fleet,
                old_integrity, fleet.integrity, star
            )
            msg = factory.new_message()
            msg.year = self.game.year
            msg.save()

        real_shipyards_spent = service_units / rate
        return max(0.0, float(remaining_shipyards) - real_shipyards_spent)

    def _repair_fleets_at_star(self, star, available_shipyards):
        """Service fleets at a colony, applying diplomacy-based visitor rates."""
        from .models import Fleet

        if available_shipyards <= 0 or not star or not star.player:
            return

        remaining_shipyards = float(available_shipyards)
        owner = star.player
        owner_stance_map = self._stance_map_for_player(owner)

        owner_fleets = list(Fleet.objects.filter(
            game=self.game,
            player=owner,
            x=star.x,
            y=star.y,
        ).order_by('id'))
        for fleet in owner_fleets:
            if remaining_shipyards <= 0:
                return
            remaining_shipyards = self._service_fleet_with_shipyards(
                fleet,
                remaining_shipyards,
                1.0,
                star,
            )

        visitor_fleets = list(Fleet.objects.filter(
            game=self.game,
            x=star.x,
            y=star.y,
        ).exclude(player=owner).exclude(player__isnull=True).exclude(player__defeated=True).order_by('id'))
        for fleet in visitor_fleets:
            if remaining_shipyards <= 0:
                break
            service_rate = player_permission_value(
                owner,
                fleet.player,
                PERMISSION_SHIPYARD_REPAIR_RATE,
                default=0.0,
                stance_map=owner_stance_map,
            )
            remaining_shipyards = self._service_fleet_with_shipyards(
                fleet,
                remaining_shipyards,
                service_rate,
                star,
            )

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
def combine_speed_advantages(*advantages):
    """Combine bounded speed advantages and cap the result within +/-0.99.

    This keeps moderate race/hull bonuses feeling additive while preventing
    stacked sources from producing runaway >1 warp-equivalent advantages.
    """
    total = 0.0
    for raw in advantages:
        try:
            value = float(raw or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0.99:
            value = 0.99
        elif value < -0.99:
            value = -0.99
        if value:
            total += atanh(value)
    combined = tanh(total) if total else 0.0
    if combined > 0.99:
        return 0.99
    if combined < -0.99:
        return -0.99
    return combined
