class HabitabilityRules:
    """Pure-python habitability rules shared between server and Brython."""
    HABITABILITY_BUDGET = 6.0
    HABITABILITY_COST_MULTIPLIER = 1.0
    ENVS = ['gravity', 'temperature', 'radiation']

    def __init__(self, centers, widths, budget=None, envs=None, cost_multiplier=None):
        self.envs = list(envs or self.ENVS)
        self.centers = {env: float(centers[env]) for env in self.envs}
        self.widths = {env: float(widths[env]) for env in self.envs}
        self.budget = float(self.HABITABILITY_BUDGET if budget is None else budget)
        self.cost_multiplier = float(
            self.HABITABILITY_COST_MULTIPLIER if cost_multiplier is None else cost_multiplier
        )

    @classmethod
    def from_source(cls, source, budget=None, envs=None, cost_multiplier=None):
        envs = list(envs or cls.ENVS)
        centers = {env: getattr(source, f'{env}_center') for env in envs}
        widths = {env: getattr(source, f'{env}_width') for env in envs}
        return cls(centers, widths, budget=budget, envs=envs, cost_multiplier=cost_multiplier)

    def hab_min(self, env):
        return self.centers[env] - self.widths[env] / 2

    def hab_max(self, env):
        return self.centers[env] + self.widths[env] / 2

    def width_cost(self):
        return sum(self.widths[env] for env in self.envs) * self.cost_multiplier

    def center_cost(self):
        return sum(1.0 - abs(self.centers[env] - 1.0) for env in self.envs) * self.cost_multiplier

    def habitability_cost(self):
        return self.width_cost() + self.center_cost()

    def total_cost(self):
        return self.habitability_cost()

    def per_env_cost(self, env):
        base = self.widths[env] + (1.0 - abs(self.centers[env] - 1.0))
        return base * self.cost_multiplier

    def validate(self):
        errors = []
        for env in self.envs:
            center = self.centers[env]
            width = self.widths[env]
            half = width / 2
            if center - half < 0.0:
                errors.append(f'{env.title()} range extends below 0')
            if center + half > 2.0:
                errors.append(f'{env.title()} range extends above 2')
            if width < 0:
                errors.append(f'{env.title()} width cannot be negative')
        if self.total_cost() > self.budget:
            errors.append(
                f'Habitability cost ({self.total_cost():.2f}) exceeds budget ({self.budget})'
            )
        return errors


class RaceCreationRules(HabitabilityRules):
    HABITABILITY_BUDGET = 120.0
    HABITABILITY_COST_MULTIPLIER = 4.0
    WIDTH_COST_MULTIPLIER = 2.0
    MIN_WIDTH = 0.1
    CENTER_STEP = 0.05
    DEFAULT_STARTING_COLONISTS = 20
    DEFAULT_STARTING_MINES = 4
    DEFAULT_STARTING_FACTORIES = 2
    DEFAULT_STARTING_LABS = 1
    DEFAULT_STARTING_SHIPYARDS = 1
    DEFAULT_STARTING_FLEETS = 2
    DEFAULT_STARTING_TECH_LEVEL = 3
    DEFAULT_RACE_TYPE_POINTS_BALANCE = 0.0

    def __init__(
        self,
        centers,
        widths,
        starting_colonists=None,
        starting_mines=None,
        starting_factories=None,
        starting_labs=None,
        starting_shipyards=None,
        starting_fleets=None,
        starting_tech_level=None,
        starting_tech_level_cost=None,
        race_type_points_balance=None,
        convert_unused_buildpoints_to_research=False,
        singular_research=False,
        fixed_homeworld=False,
        budget=None,
        envs=None,
    ):
        super().__init__(centers, widths, budget=budget, envs=envs, cost_multiplier=self.HABITABILITY_COST_MULTIPLIER)
        if starting_colonists is None:
            starting_colonists = self.DEFAULT_STARTING_COLONISTS
        if starting_mines is None:
            starting_mines = self.DEFAULT_STARTING_MINES
        if starting_factories is None:
            starting_factories = self.DEFAULT_STARTING_FACTORIES
        if starting_labs is None:
            starting_labs = self.DEFAULT_STARTING_LABS
        if starting_shipyards is None:
            starting_shipyards = self.DEFAULT_STARTING_SHIPYARDS
        if starting_fleets is None:
            starting_fleets = self.DEFAULT_STARTING_FLEETS
        if starting_tech_level is None:
            starting_tech_level = self.DEFAULT_STARTING_TECH_LEVEL
        if race_type_points_balance is None:
            race_type_points_balance = self.DEFAULT_RACE_TYPE_POINTS_BALANCE
        self.starting_colonists = int(starting_colonists)
        self.starting_mines = int(starting_mines)
        self.starting_factories = int(starting_factories)
        self.starting_labs = int(starting_labs)
        self.starting_shipyards = int(starting_shipyards)
        self.starting_fleets = int(starting_fleets)
        self.starting_tech_level = int(starting_tech_level)
        self.race_type_points_balance = float(race_type_points_balance or 0.0)
        if starting_tech_level_cost is None:
            starting_tech_level_cost = self._default_starting_tech_level_cost(
                self.starting_tech_level
            )
        self.starting_tech_level_cost_value = max(0.0, float(starting_tech_level_cost or 0.0))
        self.convert_unused_buildpoints_to_research = bool(convert_unused_buildpoints_to_research)
        self.singular_research = bool(singular_research)
        self.fixed_homeworld = bool(fixed_homeworld)

    def width_cost(self):
        # Keep width=1.0 unchanged, but increase cost curve as width approaches 2.0.
        # Narrower-than-default ranges stay linear; only wider-than-default ranges
        # get the surcharge curve.
        width_total = sum(
            self._effective_width_cost(self.widths[env]) for env in self.envs
        )
        return width_total * self.WIDTH_COST_MULTIPLIER * self.cost_multiplier

    def per_env_cost(self, env):
        base = (
            self._effective_width_cost(self.widths[env]) * self.WIDTH_COST_MULTIPLIER
            + (1.0 - abs(self.centers[env] - 1.0))
        )
        return base * self.cost_multiplier

    @staticmethod
    def _effective_width_cost(width):
        width = float(width)
        if width <= 1.0:
            return width
        return width + 0.5 * ((width - 1.0) ** 2)

    def colonist_cost(self):
        return max(0, self.starting_colonists)

    def mines_cost(self):
        return max(0, self.starting_mines)

    def factories_cost(self):
        return max(0, self.starting_factories) * 2

    def labs_cost(self):
        return max(0, self.starting_labs) * 4

    def shipyards_cost(self):
        return max(0, self.starting_shipyards) * 4

    def fleets_cost(self):
        return max(0, self.starting_fleets) * 8

    def starting_tech_level_cost(self):
        return self.starting_tech_level_cost_value

    def race_type_balance_cost(self):
        return self.race_type_points_balance

    @staticmethod
    def _default_starting_tech_level_cost(level):
        level = max(0, int(level or 0))
        if level <= 0:
            return 0.0
        rp_prev_prev = 50
        rp_prev = 80
        total_rp = 0
        for idx in range(1, level + 1):
            if idx == 1:
                rp = 50
            elif idx == 2:
                rp = 80
            else:
                rp = rp_prev + rp_prev_prev
                rp_prev_prev = rp_prev
                rp_prev = rp
            total_rp += rp
        return float(total_rp) / 10.0

    def convert_unused_buildpoints_cost(self):
        return 20 if self.convert_unused_buildpoints_to_research else 0

    def singular_research_savings(self):
        return 16 if self.singular_research else 0

    def fixed_homeworld_savings(self):
        return 16 if self.fixed_homeworld else 0

    def total_cost(self):
        return (self.habitability_cost() + self.colonist_cost() +
                self.mines_cost() + self.factories_cost() +
                self.labs_cost() + self.shipyards_cost() + self.fleets_cost() +
                self.starting_tech_level_cost() + self.race_type_balance_cost() +
                self.convert_unused_buildpoints_cost() - self.singular_research_savings() -
                self.fixed_homeworld_savings())

    def validate(self):
        errors = []
        for env in self.envs:
            center = self.centers[env]
            width = self.widths[env]
            half = width / 2
            if width < self.MIN_WIDTH:
                errors.append(f'{env.title()} width cannot be below {self.MIN_WIDTH}')
            if center - half < 0.0:
                errors.append(f'{env.title()} range extends below 0')
            if center + half > 2.0:
                errors.append(f'{env.title()} range extends above 2')
            if width < 0:
                errors.append(f'{env.title()} width cannot be negative')
        if self.starting_mines < 0:
            errors.append('Starting mines cannot be negative')
        if self.starting_factories < 0:
            errors.append('Starting factories cannot be negative')
        if self.starting_labs < 0:
            errors.append('Starting labs cannot be negative')
        if self.starting_shipyards < 0:
            errors.append('Starting shipyards cannot be negative')
        if self.starting_fleets < 0:
            errors.append('Starting fleets cannot be negative')
        if self.starting_tech_level < 0:
            errors.append('Starting tech level cannot be negative')
        if self.total_cost() > self.budget:
            errors.append(
                f'Habitability cost ({self.total_cost():.2f}) exceeds budget ({self.budget})'
            )
        return errors
