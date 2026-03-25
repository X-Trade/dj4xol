"""Pure employment/staffing math shared by colony rules and tests."""


def calculate_total_jobs_count(
    mines,
    factories,
    labs,
    defenses,
    shipyards,
    colonists_per_job,
    colonists_per_shipyard,
    include_special_jobs=False,
    special_jobs=0,
):
    jobs = (
        (
            int(mines or 0) +
            int(factories or 0) +
            int(labs or 0) +
            int(defenses or 0)
        ) * int(colonists_per_job or 0)
    ) + (int(shipyards or 0) * int(colonists_per_shipyard or 0))
    if bool(include_special_jobs):
        jobs += int(special_jobs or 0)
    return max(0, int(jobs))


def calculate_employment_percent(colonists, jobs):
    colonists = int(colonists or 0)
    jobs = int(jobs or 0)
    if colonists <= 0 or jobs <= 0:
        return 0
    return min(100, jobs / float(colonists) * 100.0)


def calculate_staffing_ratio(colonists, jobs):
    colonists = int(colonists or 0)
    jobs = int(jobs or 0)
    if colonists <= 0 or jobs <= 0:
        return 0.0
    return jobs / float(colonists)


def calculate_overemployment_effectiveness(employment_ratio):
    ratio = float(employment_ratio or 0.0)
    if ratio <= 0.0:
        return 0.0
    if ratio <= 1.0:
        return 1.0
    return 1.0 / ratio


def calculate_productivity_multiplier(employment_ratio):
    """Bell-curve productivity based on employment ratio.

    Targets: 0.25x at 1%, 0.5x at 10%, 1.5x at 50%, 1.0x at 100%.
    Productivity never drops below 0.2x once any staffing exists.
    Above 100% employment, productivity declines as 1/employment.
    """
    if employment_ratio <= 0:
        return 0.0
    if employment_ratio >= 1.0:
        return 1.0 / employment_ratio

    ratio = max(0.0, min(1.0, employment_ratio))
    if ratio < 0.01:
        return 0.2 + (ratio / 0.01) * 0.05
    if ratio <= 0.1:
        return 0.25 + ((ratio - 0.01) / 0.09) * 0.25

    # Quadratic fit through (0.1, 0.5), (0.5, 1.5), (1.0, 1.0)
    a = -3.8888888889
    b = 4.8333333333
    c = 0.0555555556
    return a * ratio * ratio + b * ratio + c

