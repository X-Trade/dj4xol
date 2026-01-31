from datetime import timedelta
from math import tanh, atan2, degrees
from numpy import array as nparray, linalg
from django.utils import timezone

from .messages import (
    EnvironmentalDeathMessageFactory,
    OvercrowdingDeathMessageFactory,
    ColonyAbandonedMessageFactory,
)

# Population carrying capacity constants
BILLION = 1_000_000_000
MILLION = 1_000_000
DEFAULT_SOFT_CAP = 10 * BILLION   # Fallback if no star capacity
CAPACITY_SCALE_RATIO = 0.5        # Scale is this fraction of soft cap

TURN_INTERVALS = {
    'HOURLY': timedelta(hours=1),
    'DAILY': timedelta(days=1),
    'WEEKLY': timedelta(weeks=1),
}


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


def calculate_habitability_factor(player, star):
    """Calculate raw habitability factor without capacity modifier.

    Returns a factor where:
    - Perfect habitability (all envs at center): 1.0
    - Edge habitability (all envs at min/max): 0.0
    - Outside range: negative
    """
    factor = 0
    for env in ['gravity', 'temperature', 'radiation']:
        factor += habitability_proportion(
            player.hab_min(env),
            player.hab_max(env),
            getattr(player, f'{env}_center'),
            getattr(star, env)
        )
    # Average the three factors (0-1 range when fully habitable)
    return factor / 3.0


def calculate_growth_factor(player, star):
    """Calculate population growth factor based on habitability and carrying capacity.

    Returns a factor where:
    - Perfect habitability (all envs at center): ~0.5 (50% growth) at low pop
    - Edge habitability (all envs at min/max): 0 (no growth)
    - Outside range: negative (linear decline, handled by apply_population_change)
    - High population: reduced by carrying capacity (tanh curve)
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
        # Negative factors passed through directly for linear decline
        return hab_factor

class GameTurn():
    """Generate a turn for a game."""
    def __init__(self, game):
        self.game = game

    def generate_turn(self):
        """Generate a turn for the game. Requires at least one player."""
        if not self.game.players.exists():
            raise Exception("cannot generate turn for game with no players")
        for _ in range(self.game.years_per_turn):
            self._process_year()
        self.game.last_generated = timezone.now()
        self.game.next_generation = self._calculate_next_generation()
        self._reset_turn_ins()
        self.game.save()

    def _process_year(self):
        """Process a single year of game time."""
        self.fleet_movements()
        self.population_growth()
        self.clear_empty_planets()
        self.check_join_deadline()
        self.game.year += 1

    def _calculate_next_generation(self):
        """Calculate next generation time based on turn scheme."""
        interval = TURN_INTERVALS.get(self.game.turn_scheme)
        return timezone.now() + interval if interval else None

    def _reset_turn_ins(self):
        """Reset turned_in status for all players."""
        self.game.players.update(turned_in=False)

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
        for fleet in self.game.fleets.all():
            self.move_fleet(fleet).save()

    def move_fleet(self, fleet):
        order = fleet.orders.first()  # this is the current order
        if not order:
            return fleet
        if order.target_star:
            x = order.target_star.x
            y = order.target_star.y
        elif order.target_fleet:
            x = order.target_fleet.x
            y = order.target_fleet.y
        elif order.x and order.y:
            x = order.x
            y = order.y
        else:
            raise Exception("invalid order %s" % (str(order.id)))

        target = nparray([x, y])
        position = nparray([fleet.x, fleet.y])
        vector = target - position
        distance = linalg.norm(vector)
        print("position: %s" % (str(position)))
        print("target:   %s" % (str(target)))
        print("vector:   %s" % (str(vector)))
        print("distance: %s" % (str(distance)))

        # Calculate heading from movement direction (where they came from)
        # 0 = north, 90 = east, 180 = south, 270 = west
        dx, dy = vector[0], vector[1]
        # atan2(dx, -dy) gives angle from north, add 180 to point back
        fleet.heading = (degrees(atan2(dx, -dy)) + 180) % 360

        if int(distance) <= order.warpfactor:
            fleet.x = x
            fleet.y = y
            if order.repeat:
                # this may not work....
                neworder = order
                neworder.id = None
                neworder.save()
            order.delete()
        else:
            normalised_vector = vector / distance
            print("normal:   %s" % (str(normalised_vector)))
            new_position = position + (normalised_vector * order.warpfactor)
            fleet.x = int(new_position[0])
            fleet.y = int(new_position[1])
        return fleet

    def population_growth(self):
        """Apply population growth/decline to all colonized planets."""
        for star in self.game.stars.filter(colonists__gt=0, player__isnull=False):
            player = star.player
            old_pop = star.colonists

            # Calculate habitability and capacity factors separately for messaging
            hab_factor = calculate_habitability_factor(player, star)
            cap = effective_capacity(player, star)
            cap_mod = capacity_modifier(star.colonists, cap)

            if hab_factor < 0:
                # Environmental deaths - uninhabitable world
                factor = hab_factor  # Pass through negative factor
                factor *= player.race_type.population_growth_multiplier
                star.colonists = apply_population_change(star.colonists, factor)
                deaths = old_pop - star.colonists
                if deaths > 0:
                    self._create_environmental_death_message(player, star, deaths)
            else:
                # Habitable world - apply growth with capacity modifier
                factor = (hab_factor ** 2) / 2  # Dampen growth
                factor *= cap_mod
                factor *= player.race_type.population_growth_multiplier
                star.colonists = apply_population_change(star.colonists, factor)
                change = star.colonists - old_pop
                if change < 0:
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


def apply_population_change(population, factor):
    """Apply population growth or decline based on factor.

    Positive factor: additive growth (pop += pop * factor)
    Negative factor: linear decline (pop *= survival_rate), min 1 loss to prevent infinite decay
    """
    if factor >= 0:
        return population + int(population * factor)
    else:
        # Linear decline: survival_rate = 1 - |factor|, capped at 0% survival
        survival_rate = max(0, 1 - abs(factor))
        new_pop = int(population * survival_rate)
        # Ensure at least 1 colonist dies to prevent infinite decay
        new_pop = min(new_pop, population - 1)
        return max(0, new_pop)
