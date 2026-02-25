import random


def random_ironium_yield():
    """Random ironium yield with a stronger high-end bias."""
    base = random.random()
    biased = 0.2 + (base ** 0.5) * 0.75
    return int(biased * 100)


def random_boranium_yield():
    """Random boranium yield, slightly rarer than ironium. Average ~35%."""
    base = random.random()
    biased = 0.05 + (base ** 0.8) * 0.65  # Range 0.05-0.7
    return int(biased * 100)


def random_germanium_yield():
    """Random germanium yield, rarest of the three. Average ~25%."""
    base = random.random()
    biased = (base ** 1.2) * 0.6  # Range 0-0.6, biased low
    return int(biased * 100)


def _random_surface_stockpile(common_max, uncommon_max, rare_max, jackpot_max):
    """Generate surface stockpile with controlled rarity bands."""
    roll = random.random()
    if roll < 0.90:
        return random.randint(0, common_max)
    if roll < 0.985:
        return random.randint(common_max + 1, uncommon_max)
    if roll < 0.995:
        return random.randint(uncommon_max + 1, rare_max)
    return random.randint(rare_max + 1, jackpot_max)


def random_surface_ironium_init():
    """Random ironium surface stockpile (most abundant on average)."""
    return _random_surface_stockpile(
        common_max=900,
        uncommon_max=3500,
        rare_max=15000,
        jackpot_max=250000,
    )


def random_surface_boranium_init():
    """Random boranium surface stockpile (less abundant than ironium)."""
    return _random_surface_stockpile(
        common_max=550,
        uncommon_max=2200,
        rare_max=10000,
        jackpot_max=140000,
    )


def random_surface_germanium_init():
    """Random germanium surface stockpile (rarest on average)."""
    return _random_surface_stockpile(
        common_max=350,
        uncommon_max=1600,
        rare_max=7000,
        jackpot_max=100000,
    )


def random_surface_mineral_init():
    """Random non-ironium surface minerals (Boranium/Germanium legacy default)."""
    return random_surface_boranium_init()
