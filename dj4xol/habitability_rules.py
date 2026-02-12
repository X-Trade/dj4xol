class HabitabilityRules:
    """Pure-python habitability rules shared between server and Brython."""
    HABITABILITY_BUDGET = 6.0
    ENVS = ['gravity', 'temperature', 'radiation']

    def __init__(self, centers, widths, budget=None, envs=None):
        self.envs = list(envs or self.ENVS)
        self.centers = {env: float(centers[env]) for env in self.envs}
        self.widths = {env: float(widths[env]) for env in self.envs}
        self.budget = float(self.HABITABILITY_BUDGET if budget is None else budget)

    @classmethod
    def from_source(cls, source, budget=None, envs=None):
        envs = list(envs or cls.ENVS)
        centers = {env: getattr(source, f'{env}_center') for env in envs}
        widths = {env: getattr(source, f'{env}_width') for env in envs}
        return cls(centers, widths, budget=budget, envs=envs)

    def hab_min(self, env):
        return self.centers[env] - self.widths[env] / 2

    def hab_max(self, env):
        return self.centers[env] + self.widths[env] / 2

    def width_cost(self):
        return sum(self.widths[env] for env in self.envs)

    def center_cost(self):
        return sum(1.0 - abs(self.centers[env] - 1.0) for env in self.envs)

    def total_cost(self):
        return self.width_cost() + self.center_cost()

    def per_env_cost(self, env):
        return self.widths[env] + (1.0 - abs(self.centers[env] - 1.0))

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
