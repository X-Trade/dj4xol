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


def _ordered_other_indices(length, changed_idx):
    if length <= 1:
        return [changed_idx]
    result = []
    for step in range(1, length + 1):
        idx = (changed_idx + step) % length
        if idx != changed_idx:
            result.append(idx)
    return result


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
    if total < 100.0:
        deficit = int(100 - total)
        target_indices = _ordered_other_indices(len(values), idx)
        while deficit > 0:
            progressed = False
            for i in target_indices:
                if deficit <= 0:
                    break
                if values[i] < 100:
                    values[i] += 1
                    deficit -= 1
                    progressed = True
            if not progressed:
                if values[idx] < 100:
                    values[idx] += 1
                    deficit -= 1
                else:
                    break
        _updating = True
        try:
            for i, inp in enumerate(_inputs()):
                inp.value = '%d' % _clamp(values[i])
        finally:
            _updating = False
        return
    if total == 100.0:
        changed.value = '%d' % values[idx]
        return

    excess = int(total - 100)
    other_indices = _ordered_other_indices(len(values), idx)

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
