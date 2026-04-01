from __future__ import unicode_literals


MINE_BUILD_CAP = 2000
INFRASTRUCTURE_BUILD_CAP = 10000

INFRASTRUCTURE_ORDER_TO_FIELD = {
    'BUILD_MINE': 'mines',
    'BUILD_FACTORY': 'factories',
    'BUILD_LAB': 'labs',
    'BUILD_DEFENSE': 'defenses',
    'BUILD_SHIPYARD': 'shipyards',
}

INFRASTRUCTURE_ORDER_TO_CAP = {
    'BUILD_MINE': MINE_BUILD_CAP,
    'BUILD_FACTORY': INFRASTRUCTURE_BUILD_CAP,
    'BUILD_LAB': INFRASTRUCTURE_BUILD_CAP,
    'BUILD_DEFENSE': INFRASTRUCTURE_BUILD_CAP,
    'BUILD_SHIPYARD': INFRASTRUCTURE_BUILD_CAP,
}


def production_infrastructure_field(order_type):
    return INFRASTRUCTURE_ORDER_TO_FIELD.get(str(order_type or '').strip().upper())


def production_infrastructure_cap(order_type):
    return INFRASTRUCTURE_ORDER_TO_CAP.get(str(order_type or '').strip().upper())


def production_infrastructure_count(star, order_type):
    field = production_infrastructure_field(order_type)
    if not field:
        return None
    return int(getattr(star, field, 0) or 0)


def production_infrastructure_room(star, order_type, reserved=0):
    cap = production_infrastructure_cap(order_type)
    if cap is None:
        return None
    count = production_infrastructure_count(star, order_type)
    if count is None:
        return None
    return max(0, int(cap) - int(count) - max(0, int(reserved or 0)))


def remaining_order_quantity(order):
    return max(
        0,
        int(getattr(order, 'quantity', 0) or 0) -
        int(getattr(order, 'completed', 0) or 0),
    )


def queued_remaining_quantity_for_order_type(star, order_type):
    cap = production_infrastructure_cap(order_type)
    if cap is None:
        return 0
    total = 0
    for order in star.production_orders.filter(order_type=order_type):
        total += remaining_order_quantity(order)
    return max(0, int(total))


def capped_order_quantity_for_star(star, order_type, requested_quantity):
    """Clamp requested quantity so current + queued + new does not exceed cap."""
    requested = max(1, int(requested_quantity or 1))
    cap = production_infrastructure_cap(order_type)
    if cap is None:
        return requested
    reserved = queued_remaining_quantity_for_order_type(star, order_type)
    room = production_infrastructure_room(star, order_type, reserved=reserved)
    if room is None or room <= 0:
        return 0
    return min(requested, int(room))
