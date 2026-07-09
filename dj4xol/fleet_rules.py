PLAYER_FLEET_CAP = 16384


def player_fleet_count_allows_build(fleet_count):
    try:
        fleet_count = int(fleet_count or 0)
    except (TypeError, ValueError):
        fleet_count = 0
    return fleet_count < int(PLAYER_FLEET_CAP)


def player_can_build_more_fleets(player):
    if not player:
        return False
    return player_fleet_count_allows_build(player.fleets.count())
