import random

BASE_MINERAL_KEYS = ('ironium', 'boranium', 'germanium')
SECRET_RESOURCE_KEYS = ('resource_x', 'resource_y', 'resource_z')
ALL_RESOURCE_KEYS = BASE_MINERAL_KEYS + SECRET_RESOURCE_KEYS


def resource_present(star, resource_key):
    """Return True if the star has yield or surface stockpiles for a resource."""
    if not star or not resource_key:
        return False
    yield_val = int(getattr(star, f'{resource_key}_yield', 0) or 0)
    inventory_val = int(getattr(star, f'{resource_key}_inventory', 0) or 0)
    return yield_val > 0 or inventory_val > 0


def known_resource_keys(player, star):
    """Return resource keys known to the player and present on the star."""
    if not star:
        return []
    keys = []
    for key in BASE_MINERAL_KEYS:
        keys.append(key)
    for key in SECRET_RESOURCE_KEYS:
        if resource_present(star, key):
            if player and bool(getattr(player, f'discovered_{key}', False)):
                keys.append(key)
    return keys


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


def random_asteroid_field_minerals(total_min=1000, total_max=50000):
    """Generate natural asteroid field minerals (avg ~50/30/20, reduced cap)."""
    total = random.randint(int(total_min), int(total_max))
    base = (0.50, 0.30, 0.20)
    jitters = (
        random.uniform(-0.45, 0.45),
        random.uniform(-0.45, 0.45),
        random.uniform(-0.45, 0.45),
    )
    weights = [
        max(0.0, base[0] + jitters[0]),
        max(0.0, base[1] + jitters[1]),
        max(0.0, base[2] + jitters[2]),
    ]
    # Keep average iron-heavy but allow broad variance and occasional zeros.
    if weights[0] <= 0.0:
        weights[0] = random.uniform(0.05, 0.20)

    zero_idx = [idx for idx, val in enumerate(weights) if val <= 0.0]
    if len(zero_idx) > 1:
        revive = random.choice(zero_idx)
        weights[revive] = random.uniform(0.03, 0.12)

    weight_sum = sum(weights)
    if weight_sum <= 0:
        weights = list(base)
        weight_sum = sum(weights)

    iron = int(round(total * (weights[0] / weight_sum)))
    bor = int(round(total * (weights[1] / weight_sum)))
    germ = total - iron - bor

    if weights[0] > 0 and iron <= 0:
        iron = 1
    if weights[1] > 0 and bor <= 0:
        bor = 1
    if weights[2] > 0 and germ <= 0:
        germ = 1

    remainder = total - (iron + bor + germ)
    if remainder != 0:
        iron = max(0, iron + remainder)

    if sum(1 for val in (iron, bor, germ) if val == 0) > 1:
        if bor == 0 and germ == 0:
            bor = 1
            germ = 1
            iron = max(0, total - bor - germ)
        elif iron == 0:
            iron = 1
            if bor == 0:
                bor = 1
            if germ == 0:
                germ = 1
            remainder = total - (iron + bor + germ)
            if remainder != 0:
                iron = max(0, iron + remainder)

    return iron, bor, germ


def random_ancient_debris_minerals(total_min=1000, total_max=100000):
    """Generate mineral totals for ancient debris (50/20/20 + 10% secret)."""
    total = random.randint(int(total_min), int(total_max))
    secret_key = random.choice(SECRET_RESOURCE_KEYS)
    secret_amount = int(round(total * 0.10))
    base_total = total - secret_amount
    iron = int(round(base_total * 0.50))
    bor = int(round(base_total * 0.20))
    germ = base_total - iron - bor

    res_x = res_y = res_z = 0
    if secret_key == 'resource_x':
        res_x = secret_amount
    elif secret_key == 'resource_y':
        res_y = secret_amount
    else:
        res_z = secret_amount

    return iron, bor, germ, res_x, res_y, res_z
