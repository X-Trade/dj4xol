from datetime import timedelta
from math import tanh, atan2, degrees
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
    ColoniseFailedNoStarMessageFactory,
    ColoniseFailedNoColonistsMessageFactory,
    ProductionSummaryMessageFactory,
    FleetWarpDamageMessageFactory,
    FleetWarpDestroyedMessageFactory,
    FleetMergedMessageFactory,
)
import random

# Population carrying capacity constants
BILLION = 1_000_000_000
MILLION = 1_000_000
DEFAULT_SOFT_CAP = 10 * BILLION   # Fallback if no star capacity
CAPACITY_SCALE_RATIO = 0.5        # Scale is this fraction of soft cap

# Fleet movement behavior constants
ALLOW_MULTIPLE_ORDERS_PER_TURN = False  # Set to True to allow processing multiple orders per turn

TURN_INTERVALS = {
    'HOURLY': timedelta(hours=1),
    'DAILY': timedelta(days=1),
    'WEEKLY': timedelta(weeks=1),
}

# Random event probability per colonized star per turn
RANDOM_EVENT_CHANCE = 0.01  # 1%

# Warp damage constants
WARP_DESTRUCTION_THRESHOLD = 10  # Warp speed at which destruction becomes possible
WARP_DESTRUCTION_CHANCE = 0.30   # 30% chance of instant destruction at warp >= 10


def capacity_modifier(population, soft_cap):
    """Returns a modifier that reduces growth at high populations.

    Uses tanh curve centered at soft_cap:
    - At 10% of cap: ~95% of normal growth
    - At 50% of cap: ~76% of normal growth
    - At soft_cap: 0% growth
    - Above soft_cap: negative growth (population decline)
    - At 200% of cap: ~-96% (rapid decline)
    """
    scale = soft_cap * CAPACITY_SCALE_RATIO
    return -tanh((population - soft_cap) / scale)


def effective_capacity(player, star):
    """Calculate effective carrying capacity for a star based on habitability.

    Returns capacity in colonists (not millions).
    Habitability factor ranges from 0 (uninhabitable) to 1 (perfect).
    """
    # Calculate habitability factor (average of 3 environmental proportions, clamped 0-1)
    hab_factor = 0
    for env in ['gravity', 'temperature', 'radiation']:
        proportion = habitability_proportion(
            player.hab_min(env),
            player.hab_max(env),
            getattr(player, f'{env}_center'),
            getattr(star, env)
        )
        hab_factor += max(0, proportion)  # Clamp negative to 0
    hab_factor = hab_factor / 3.0

    # base_capacity is in millions, convert to actual colonists
    base = star.base_capacity * MILLION
    return int(base * hab_factor) if hab_factor > 0 else MILLION  # Minimum 1m capacity


def habitability_proportion(hab_min, hab_max, centre, value):
    """Returns 1 at centre, 0 at min/max edges, negative outside range."""
    if value == centre:
        return 1.0
    elif value > centre:
        return 1.0 - (value - centre) / (hab_max - centre)
    else:
        return 1.0 - (centre - value) / (centre - hab_min)


# Economic constants
COLONISTS_PER_JOB = 1000  # Each mine/factory employs this many colonists
BUILDPOINTS_PER_FACTORY = 10  # Each factory produces this many buildpoints per turn
KT_PER_MINE = 10  # Each mine extracts this many kt of minerals per turn
YIELD_DEPLETION_RATE = 0.00001  # Yield drops by this % per kt extracted (0.001% per kt)
HOMEWORLD_MIN_YIELD = 30  # Homeworld yields never drop below this percentage


def calculate_employment_percent(star):
    """Calculate employment percentage based on mines, factories, and defenses.

    Each mine, factory, and defense employs COLONISTS_PER_JOB colonists.
    Returns 0-100, capped at 100%.
    """
    if star.colonists == 0:
        return 0
    jobs = (star.mines + star.factories + star.defenses) * COLONISTS_PER_JOB
    return min(100, jobs / star.colonists * 100)


def calculate_available_buildpoints(star):
    """Calculate buildpoints available this turn from factories.

    Buildpoints represent factory labour capacity and do not accumulate.
    Only fully staffed factories produce buildpoints - if there aren't
    enough colonists to staff all infrastructure, output is proportionally reduced.
    """
    if star.factories == 0:
        return 0
    jobs = (star.mines + star.factories + star.defenses) * COLONISTS_PER_JOB
    if jobs == 0:
        return 0
    staffing_ratio = min(1.0, star.colonists / jobs)
    return int(star.factories * BUILDPOINTS_PER_FACTORY * staffing_ratio)


def calculate_consumed_buildpoints(star):
    """Calculate buildpoints consumed by production this turn."""
    return star.buildpoints_consumed


def calculate_productivity_percent(star):
    """Calculate productivity percentage based on buildpoints consumed.

    Productivity is the percentage of available buildpoints that were
    consumed this turn. Capped at 100%.
    """
    available = calculate_available_buildpoints(star)
    if available == 0:
        return 0
    consumed = calculate_consumed_buildpoints(star)
    return min(100, consumed / available * 100)


def calculate_economy_percent(star):
    """Calculate economy percentage from employment and productivity.

    economy% = employment%/2 + productivity%/2
    Returns 0-100, minimum 0%.
    """
    employment = calculate_employment_percent(star)
    productivity = calculate_productivity_percent(star)
    return (employment - 50) + (productivity - 25) / 2


def calculate_economy_factor(star):
    """Calculate economy factor as a coefficient (0-1 range).

    Converts economy percentage to the same scale as environmental factors.
    """
    return calculate_economy_percent(star) / 100


def calculate_habitability_factor(player, star):
    """Calculate raw habitability factor without capacity modifier.

    Returns a factor where:
    - Perfect habitability (all envs at center): 1.0
    - Edge habitability (all envs at min/max): 0.0
    - Outside range: negative

    Economy factor is added to environmental factors before averaging,
    but the /3 divisor is kept. This allows economic activity to
    temporarily boost growth beyond what environment alone would allow.
    """
    factor = 0
    for env in ['gravity', 'temperature', 'radiation']:
        factor += habitability_proportion(
            player.hab_min(env),
            player.hab_max(env),
            getattr(player, f'{env}_center'),
            getattr(star, env)
        )
    # Add economy factor before averaging
    factor += calculate_economy_factor(star)
    # Average using the original /3 divisor (economy is a bonus)
    return factor / 6.0 # changed to nerf growth


def calculate_growth_factor(player, star):
    """Calculate population growth factor based on habitability and carrying capacity.

    Returns a factor where:
    - Perfect habitability (all envs at center): ~0.25 (25% growth) at low pop
    - Edge habitability (all envs at min/max): 0 (no growth)
    - Outside range: negative (linear decline)
    - High population: reduced by carrying capacity (tanh curve)

    The returned factor should be multiplied by race_type.population_growth_multiplier
    before being passed to apply_population_change().
    """
    hab_factor = calculate_habitability_factor(player, star)

    if hab_factor >= 0:
        # Dampen growth: max ~0.5 at perfect habitability
        factor = (hab_factor ** 2) / 2
        # Apply carrying capacity modifier (reduces growth at high populations)
        cap = effective_capacity(player, star)
        factor *= capacity_modifier(star.colonists, cap)
        return factor
    else:
        # Negative factor for environmental deaths
        return hab_factor

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
        self.mining()
        self.production()
        self.population_growth()
        self.random_events()
        self.clear_empty_planets()
        self.check_join_deadline()
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
        # Get fleet IDs first, then fetch fresh for each processing
        # This ensures we see changes made by other fleet's transfers
        fleet_ids = list(self.game.fleets.values_list('id', flat=True))
        for fleet_id in fleet_ids:
            try:
                fleet = self.game.fleets.get(id=fleet_id)
            except self.game.fleets.model.DoesNotExist:
                continue  # Fleet was deleted (e.g., by colonise order)
            result = self.move_fleet(fleet)
            if result is not None:
                result.save()

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

    def move_fleet(self, fleet):
        """Process fleet orders, with configurable behavior for multiple orders per turn."""

        if ALLOW_MULTIPLE_ORDERS_PER_TURN:
            # Legacy behavior: process multiple orders per turn (old system)
            return self._move_fleet_legacy(fleet)
        else:
            # New behavior: process only one order per turn (more realistic)
            return self._move_fleet_single_order(fleet)

    def _move_fleet_single_order(self, fleet):
        """Process fleet orders: no order executes twice per turn, transfers passthrough, moves block."""
        # Snapshot orders at start of turn to avoid processing newly created repeat orders
        # Transfer orders: execute once and continue to next order (passthrough)
        # Move orders: execute once and stop processing (blocking)

        # Snapshot all current orders to prevent processing repeat orders created this turn
        orders_to_process = list(fleet.orders.all())

        for order in orders_to_process:
            # Check if order still exists (might have been deleted by previous processing)
            if not fleet.orders.filter(id=order.id).exists():
                continue

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

            elif order.order_type == 'MOVE':
                # Try to execute move order
                move_result = self._move_toward_destination(fleet, order)
                if move_result == 'destroyed':
                    # Fleet destroyed by warp damage
                    return None
                if move_result is True:
                    # Reached destination - handle repeat and STOP
                    self._handle_repeating_order(order)
                    order.delete()
                # BLOCKING: Whether reached or still moving, STOP processing
                break

            elif order.order_type == 'COLONISE':
                colonise_result = self._try_execute_colonise(fleet, order)
                if colonise_result == 'executed':
                    # Fleet is deleted, return None so caller doesn't try to save it
                    return None
                elif colonise_result == 'waiting':
                    break  # Wait for fleet to reach destination

            elif order.order_type == 'MERGE':
                merge_result = self._execute_merge_order(fleet, order)
                if merge_result == 'executed':
                    # Source fleet deleted, return None so caller doesn't save
                    return None
                elif merge_result == 'waiting':
                    break  # Wait for fleets to be at same location
                # 'invalid' falls through to continue to next order
            else:
                # Unknown order type, just remove it
                order.delete()
                continue

        return fleet

    def _move_fleet_legacy(self, fleet):
        """Legacy fleet processing: multiple orders per turn (potentially problematic)."""
        processed_orders = 0
        max_orders_per_turn = 10  # Prevent infinite loops

        while processed_orders < max_orders_per_turn:
            order = fleet.orders.first()
            if not order:
                break

            if order.order_type == 'TRANSFER':
                # Try to execute transfer immediately
                transfer_result = self._try_execute_transfer(fleet, order)
                if transfer_result == 'executed':
                    # Transfer completed, delete order and continue
                    self._handle_repeating_order(order)
                    order.delete()
                    processed_orders += 1
                    continue
                elif transfer_result == 'waiting':
                    # Transfer blocked waiting for conditions, stop processing
                    break

            elif order.order_type == 'MOVE':
                # Regular move order
                move_result = self._move_toward_destination(fleet, order)
                if move_result == 'destroyed':
                    # Fleet destroyed by warp damage
                    return None
                if move_result is True:
                    # Reached destination
                    self._handle_repeating_order(order)
                    order.delete()
                    processed_orders += 1
                    # Continue to next order (might be a transfer)
                    continue
                else:
                    # Still moving, stop processing
                    break
            else:
                # Unknown order type
                order.delete()
                processed_orders += 1
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
        try:
            dest_x, dest_y = order.get_destination_coordinates()
        except ValueError:
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
        try:
            x, y = order.get_destination_coordinates()
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
        warp_speed = order.warpfactor if order.order_type == 'MOVE' else 5

        # Check for warp damage before moving
        damage_result = self._check_warp_damage(fleet, warp_speed, order)
        if damage_result == 'destroyed':
            return 'destroyed'

        if int(distance) <= warp_speed:
            # Fleet reaches destination
            fleet.x = x
            fleet.y = y
            return True
        else:
            # Fleet moves toward destination but doesn't reach it
            normalised_vector = vector / distance
            new_position = position + (normalised_vector * warp_speed)
            fleet.x = int(new_position[0])
            fleet.y = int(new_position[1])
            if (fleet.x, fleet.y) == (x, y):
                return True
            return False

    def _check_warp_damage(self, fleet, warp_speed, order):
        """Check if fleet takes damage from exceeding safe warp speed.

        Returns: 'destroyed', 'damaged', or 'safe'
        """
        if warp_speed <= fleet.max_safe_warp:
            return 'safe'

        excess_warp = warp_speed - fleet.max_safe_warp

        # At warp >= 10 and above safe speed: 30% instant destruction chance
        if warp_speed >= WARP_DESTRUCTION_THRESHOLD:
            if random.random() < WARP_DESTRUCTION_CHANCE:
                self._handle_warp_destruction(fleet, warp_speed, from_damage=False)
                return 'destroyed'

        # Damage chance: 15% per excess warp factor
        damage_chance = excess_warp * 0.15
        if random.random() < damage_chance:
            return self._apply_warp_damage(fleet, warp_speed, excess_warp, order)

        return 'safe'

    def _apply_warp_damage(self, fleet, warp_speed, excess_warp, order):
        """Apply damage effects from exceeding safe warp speed.

        Returns: 'destroyed' if integrity drops to 0, 'damaged' otherwise
        """
        # Integrity loss: 5-15% per excess warp factor
        integrity_loss = sum(
            random.randint(5, 15) for _ in range(excess_warp)
        )
        integrity_loss = min(integrity_loss, fleet.integrity)

        # Cargo loss: 2-10% per excess warp factor
        cargo_loss_percent = sum(
            random.randint(2, 10) for _ in range(excess_warp)
        ) / 100.0

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
        """Destroy fleet and create destruction message."""
        factory = FleetWarpDestroyedMessageFactory(
            self.game, fleet.player, fleet.name, warp_speed,
            fleet.x, fleet.y, from_damage
        )
        msg = factory.new_message()
        msg.year = self.game.year
        msg.save()
        fleet.delete()

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
            FleetOrders.objects.create(
                game=self.game,
                fleet=order.fleet,
                order_type=order.order_type,
                repeat=True,
                warpfactor=order.warpfactor,
                x=order.x,
                y=order.y,
                target_star=order.target_star,
                target_fleet=order.target_fleet,
                transfer_type=order.transfer_type,
                transfer_ironium=order.transfer_ironium,
                transfer_boranium=order.transfer_boranium,
                transfer_germanium=order.transfer_germanium,
                transfer_colonists=order.transfer_colonists,
            )

    def _execute_transfer_order(self, fleet, order):
        """Execute a transfer order when fleet reaches destination.

        Returns:
        - 'executed': Transfer completed successfully
        - 'waiting': Transfer blocked waiting for target
        """
        # Get the target object based on order parameters
        target_obj = None
        target_x, target_y = order.get_destination_coordinates()

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

        else:
            # Transfer to coordinates - look for objects there
            possible_targets = list(self.game.stars.filter(x=target_x, y=target_y))
            if possible_targets:
                target_obj = possible_targets[0]  # Use first star found
            else:
                print(f"No transfer target found at coordinates ({target_x}, {target_y})")
                return 'waiting'  # Wait for a target to appear

        # Verify fleet is actually at the transfer location
        if fleet.x != target_x or fleet.y != target_y:
            print(f"Transfer error: Fleet {fleet.name} not at transfer location")
            return 'executed'  # Remove invalid order

        # Execute transfer based on target type
        from .models import Star, Fleet
        if isinstance(target_obj, Star):
            self._transfer_with_star(fleet, order, target_obj)
            return 'executed'
        elif isinstance(target_obj, Fleet):
            self._transfer_with_fleet(fleet, order, target_obj)
            return 'executed'
        else:
            print(f"Transfer to {type(target_obj)} not yet implemented")
            return 'executed'  # Remove unsupported order

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

    def _try_execute_colonise(self, fleet, order):
        """Try to execute a colonise order.

        Colonise orders execute when the fleet is at the target star location.
        The fleet is destroyed and all cargo + bonus materials are deposited.

        Returns:
        - 'executed': Colonise completed, fleet destroyed
        - 'waiting': Waiting for fleet to reach destination
        """
        try:
            dest_x, dest_y = order.get_destination_coordinates()
        except ValueError:
            return 'executed'  # Invalid order, treat as executed to remove it

        # Check if fleet is at the colonise destination
        if fleet.x != dest_x or fleet.y != dest_y:
            return 'waiting'

        # Fleet is at destination, execute colonise
        return self._execute_colonise_order(fleet, order)

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
            dest_x, dest_y = order.get_destination_coordinates()
            star = Star.objects.filter(game=self.game, x=dest_x, y=dest_y).first()

        if not star:
            # No star at location, cannot colonise - create message and delete order
            dest_x, dest_y = order.get_destination_coordinates()
            factory = ColoniseFailedNoStarMessageFactory(
                self.game, fleet.player, fleet.name, dest_x, dest_y,
                target_star=order.target_star  # May be None if order used coordinates
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

        # Build cargo summary for message (before transaction)
        cargo_parts = []
        if ironium > 0:
            cargo_parts.append(f"{ironium}kt ironium")
        if boranium > 0:
            cargo_parts.append(f"{boranium}kt boranium")
        if germanium > 0:
            cargo_parts.append(f"{germanium}kt germanium")
        if colonists_kt > 0:
            cargo_parts.append(f"{colonists_kt}k colonists")
        cargo_summary = ", ".join(cargo_parts) if cargo_parts else "no cargo"

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
                self.game, player, fleet_name, star, cargo_summary, total_bonus
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

        # Merge attributes into target fleet
        target_fleet.ship_count = total_ships
        target_fleet.cargo_capacity += source_fleet.cargo_capacity
        target_fleet.dry_mass += source_fleet.dry_mass
        target_fleet.max_safe_warp = min(
            target_fleet.max_safe_warp, source_fleet.max_safe_warp
        )
        target_fleet.integrity = avg_integrity

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

    def population_growth(self):
        """Apply population growth/decline to all colonized planets."""
        for star in self.game.stars.filter(colonists__gt=0, player__isnull=False):
            player = star.player
            old_pop = star.colonists

            factor = calculate_growth_factor(player, star)
            factor *= player.race_type.population_growth_multiplier
            star.colonists = apply_population_change(star.colonists, factor)
            change = star.colonists - old_pop

            if change < 0 and star.colonists > 0:
                if factor < 0:
                    # Environmental deaths - uninhabitable world
                    self._create_environmental_death_message(player, star, -change)
                else:
                    # Deaths due to overcrowding
                    self._create_overcrowding_death_message(player, star, -change)

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

            total_extraction = star.mines * KT_PER_MINE

            # Check if this is a homeworld (yields don't drop below minimum)
            is_homeworld = star.homeworld_of.exists()
            min_yield = HOMEWORLD_MIN_YIELD if is_homeworld else 0

            # Process each resource
            for resource in ['ironium_yield', 'boranium_yield', 'germanium_yield']:
                yield_val = getattr(star, resource)
                if yield_val == 0:
                    continue

                # Calculate extraction for this resource
                extraction = total_extraction * yield_val / total_yield

                # Handle fractional amounts with random chance
                whole_kt = int(extraction)
                fractional = extraction - whole_kt
                if fractional > 0 and random.random() < fractional:
                    whole_kt += 1

                if whole_kt > 0:
                    # Add to surface inventory - map yield field to inventory field
                    inventory_field = resource.replace('_yield', '_inventory')
                    setattr(star, inventory_field, getattr(star, inventory_field) + whole_kt)

                    # Linear yield depletion proportional to extraction
                    depletion = whole_kt * YIELD_DEPLETION_RATE
                    whole_depletion = int(depletion)
                    fractional = depletion - whole_depletion
                    if fractional > 0 and random.random() < fractional:
                        whole_depletion += 1
                    if whole_depletion > 0:
                        new_yield = max(min_yield, yield_val - whole_depletion)
                        setattr(star, resource, new_yield)

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
        """
        from .models import Star, ProductionOrder, PRODUCTION_COSTS
        for star in Star.objects.filter(game=self.game, player__isnull=False):
            star.buildpoints_consumed = 0
            colonists_busy = 0  # Track colonists busy with construction this turn
            available_bp = calculate_available_buildpoints(star)
            blocked = False

            # Track production counts for aggregate messages
            production_counts = {'mine': 0, 'factory': 0, 'defense': 0}

            for order in list(star.production_orders.order_by('position')):
                if blocked:
                    break

                cost = PRODUCTION_COSTS.get(order.order_type, {})

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

                    self._apply_production_effect(star, order, production_counts)
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

            star.save()

    def _apply_production_effect(self, star, order, production_counts):
        """Apply the effect of a completed production order."""
        if order.order_type == 'BUILD_FLEET':
            self._build_fleet(star, order)
        elif order.order_type == 'BUILD_MINE':
            self._build_mine(star)
            production_counts['mine'] += 1
        elif order.order_type == 'BUILD_FACTORY':
            self._build_factory(star)
            production_counts['factory'] += 1
        elif order.order_type == 'BUILD_DEFENSE':
            self._build_defense(star)
            production_counts['defense'] += 1
        elif order.order_type.startswith('TERRAFORM_'):
            self._apply_terraform_order(star, order)

    def _build_fleet(self, star, order):
        """Build a fleet at the given star and create notification."""
        from .models import Fleet
        player = star.player

        # Auto-generate fleet name
        fleet_count = player.fleets.count() + 1
        fleet_name = f"{player.name} Fleet {fleet_count}"

        fleet = Fleet.objects.create(
            game=self.game,
            player=player,
            name=fleet_name,
            x=star.x,
            y=star.y,
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

    def _build_defense(self, star):
        """Build a defense at the given star."""
        star.defenses += 1

    def _send_production_summary_messages(self, star, production_counts):
        """Send aggregate production messages for mines/factories/defenses.

        Only sends messages for 4+ items of a type.
        """
        player = star.player
        min_count_for_message = 4

        for production_type, count in production_counts.items():
            if count >= min_count_for_message:
                factory = ProductionSummaryMessageFactory(
                    self.game, player, star, production_type, count
                )
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
