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
    HABITABILITY_BUDGET = 34.0
    HABITABILITY_COST_MULTIPLIER = 4.0
    MIN_WIDTH = 0.1
    DEFAULT_STARTING_COLONISTS = 10

    def __init__(self, centers, widths, starting_colonists=None, budget=None, envs=None):
        super().__init__(centers, widths, budget=budget, envs=envs, cost_multiplier=self.HABITABILITY_COST_MULTIPLIER)
        if starting_colonists is None:
            starting_colonists = self.DEFAULT_STARTING_COLONISTS
        self.starting_colonists = int(starting_colonists)

    def colonist_cost(self):
        return max(0, self.starting_colonists)

    def total_cost(self):
        return self.habitability_cost() + self.colonist_cost()

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
        if self.total_cost() > self.budget:
            errors.append(
                f'Habitability cost ({self.total_cost():.2f}) exceeds budget ({self.budget})'
            )
        return errors
