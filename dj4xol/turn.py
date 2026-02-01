from datetime import timedelta
from math import tanh, atan2, degrees
from numpy import array as nparray, linalg
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
)
import random

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

# Random event probability per colonized star per turn
RANDOM_EVENT_CHANCE = 0.01  # 1%


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
        self.check_lost_fleets()
        self.terraforming()
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
        for fleet in self.game.fleets.all():
            self.move_fleet(fleet).save()

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

        # Calculate heading from movement direction (where it's going)
        # 0 = north, 90 = east, 180 = south, 270 = west
        dx, dy = vector[0], vector[1]
        # atan2(dx, -dy) gives angle from north toward target
        fleet.heading = degrees(atan2(dx, -dy)) % 360

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
                if deaths > 0 and star.colonists > 0:
                    self._create_environmental_death_message(player, star, deaths)
            else:
                # Habitable world - apply growth with capacity modifier
                factor = (hab_factor ** 2) / 2  # Dampen growth
                factor *= cap_mod
                factor *= player.race_type.population_growth_multiplier
                star.colonists = apply_population_change(star.colonists, factor)
                change = star.colonists - old_pop
                if change < 0 and star.colonists > 0:
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

    def terraforming(self):
        """Process terraforming orders for all colonized planets."""
        from .models import Star
        for star in Star.objects.filter(game=self.game, player__isnull=False):
            for order in star.production_orders.all():
                self._apply_terraform_order(star, order)

    def production(self):
        """Process production orders for all colonized planets."""
        from .models import Star
        for star in Star.objects.filter(game=self.game, player__isnull=False):
            for order in list(star.production_orders.all()):
                if order.order_type == 'BUILD_FLEET':
                    self._build_fleet(star, order)

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

        # Delete the production order
        order.delete()

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
        """Apply resource discovery - add 10-30 units to random resource."""
        resource = random.choice(['ironium', 'boranium', 'germanium'])
        qty = random.randint(10, 30)
        current = getattr(star, resource)
        setattr(star, resource, min(100, current + qty))
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
        """Apply mining accident with resource loss - 5-10% of one resource."""
        resource = random.choice(['ironium', 'boranium', 'germanium'])
        current = getattr(star, resource)
        loss_pct = random.uniform(0.05, 0.10)
        loss = max(1, int(current * loss_pct))
        setattr(star, resource, max(0, current - loss))
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
