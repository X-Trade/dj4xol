from browser import document


_updating = False


def _clamp(value):
    if value < 0:
        return 0.0
    if value > 100:
        return 100.0
    return int(round(value))


def _inputs():
    return list(document.select('.allocation-input'))


def _to_float(value, fallback=0.0):
    try:
        return float(value)
    except Exception:
        return fallback


def _on_input(ev):
    global _updating
    if _updating:
        return

    changed = ev.currentTarget
    current_inputs = _inputs()
    values = [_clamp(_to_float(inp.value)) for inp in current_inputs]
    idx = current_inputs.index(changed)
    values[idx] = _clamp(_to_float(changed.value))
    total = sum(values)
    if total <= 100.0:
        changed.value = '%d' % values[idx]
        return

    excess = int(total - 100)
    other_indices = [i for i in range(len(values)) if i != idx]

    while excess > 0:
        progressed = False
        for i in other_indices:
            if excess <= 0:
                break
            if values[i] > 0:
                values[i] -= 1
                excess -= 1
                progressed = True
        if not progressed:
            break

    if excess > 0:
        values[idx] = max(0, values[idx] - excess)

    _updating = True
    try:
        for i, inp in enumerate(_inputs()):
            inp.value = '%d' % _clamp(values[i])
    finally:
        _updating = False


for item in _inputs():
    item.bind('input', _on_input)
