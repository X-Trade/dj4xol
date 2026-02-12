from browser import document, html
from habitability_rules import HabitabilityRules

STEP = 0.1


def _round_step(value):
    return round(value, 1)


def _clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


def _read_float(input_el):
    try:
        return float(input_el.value)
    except (TypeError, ValueError):
        return 0.0


def _set_input(input_el, value):
    input_el.value = f"{_round_step(value):.1f}"


def _build_env_ui(env, center_input, width_input):
    width_row = width_input.closest('tr')
    if not width_row:
        return None

    cells = width_row.getElementsByTagName('td')
    if len(cells) < 2:
        return None

    input_cell = cells[0]
    hint_cell = cells[1]

    ui = html.DIV(Class='habitability-ui')
    bar = html.DIV(Class='env-bar')
    range_marker = html.DIV(Class='env-range')
    marker = html.DIV(Class='env-marker habitable')
    bar <= range_marker
    bar <= marker

    controls = html.DIV(Class='habitability-controls')

    shrink_btn = html.BUTTON('><', Class='habitability-button', type='button')
    grow_btn = html.BUTTON('<>', Class='habitability-button', type='button')
    down_btn = html.BUTTON('-', Class='habitability-button', type='button')
    up_btn = html.BUTTON('+', Class='habitability-button', type='button')

    shrink_btn.attrs['title'] = 'Narrow range'
    grow_btn.attrs['title'] = 'Widen range'
    down_btn.attrs['title'] = 'Shift center down'
    up_btn.attrs['title'] = 'Shift center up'

    width_group = html.SPAN(Class='habitability-group')
    width_value = html.SPAN(Class='habitability-value')
    width_buttons = html.SPAN(Class='habitability-buttons')
    width_buttons <= shrink_btn
    width_buttons <= grow_btn
    width_group <= html.SPAN('Width')
    width_group <= width_buttons
    width_group <= width_value

    center_group = html.SPAN(Class='habitability-group')
    center_value = html.SPAN(Class='habitability-value')
    center_buttons = html.SPAN(Class='habitability-buttons')
    center_buttons <= down_btn
    center_buttons <= up_btn
    center_group <= html.SPAN('Center')
    center_group <= center_buttons
    center_group <= center_value

    controls <= width_group
    controls <= center_group

    ui <= bar
    ui <= controls
    input_cell <= ui

    points = html.DIV(Class='habitability-points')
    range_value = html.SPAN(Class='habitability-range')
    points <= range_value
    hint_cell.textContent = ''
    hint_cell <= points

    return {
        'env': env,
        'center': center_input,
        'width': width_input,
        'bar': bar,
        'range_marker': range_marker,
        'marker': marker,
        'points': points,
        'range': range_value,
        'width_value': width_value,
        'center_value': center_value,
        'shrink': shrink_btn,
        'grow': grow_btn,
        'down': down_btn,
        'up': up_btn,
    }


def _apply_bar(ui, rules):
    env = ui['env']
    center = rules.centers[env]
    width = rules.widths[env]
    hab_min = rules.hab_min(env)
    hab_max = rules.hab_max(env)

    def pct(value):
        return max(0.0, min(100.0, (value / 2.0) * 100.0))

    min_pct = pct(hab_min)
    max_pct = pct(hab_max)
    center_pct = pct(center)

    ui['bar'].style.background = (
        f"linear-gradient(to right, #400000 0%, #400000 {min_pct:.1f}%, "
        f"#00aa00 {min_pct:.1f}%, #00aa00 {max_pct:.1f}%, "
        f"#400000 {max_pct:.1f}%, #400000 100%)"
    )
    ui['range_marker'].style.left = f"{min_pct:.1f}%"
    ui['range_marker'].style.width = f"{max_pct - min_pct:.1f}%"
    ui['marker'].style.left = f"{center_pct:.1f}%"


def _update_all(ui_rows, summary_value, error_box):
    centers = {ui['env']: _read_float(ui['center']) for ui in ui_rows}
    widths = {ui['env']: _read_float(ui['width']) for ui in ui_rows}
    for ui in ui_rows:
        env = ui['env']
        widths[env] = _clamp(widths[env], 0.0, 2.0)
        min_center = widths[env] / 2.0
        max_center = 2.0 - widths[env] / 2.0
        centers[env] = _clamp(centers[env], min_center, max_center)
        _set_input(ui['width'], widths[env])
        _set_input(ui['center'], centers[env])
    rules = HabitabilityRules(centers, widths)

    for ui in ui_rows:
        _apply_bar(ui, rules)
        points = rules.per_env_cost(ui['env'])
        ui['points'].text = f"{points:.2f} pts"
        ui['range'].text = f"Range {rules.hab_min(ui['env']):.1f}–{rules.hab_max(ui['env']):.1f}"
        ui['width_value'].text = f"{rules.widths[ui['env']]:.2f}"
        ui['center_value'].text = f"{rules.centers[ui['env']]:.2f}"

    total = rules.total_cost()
    summary_value.text = f"{total:.2f} / {rules.budget:.1f} pts"
    if total > rules.budget:
        summary_value.classList.add('over-budget')
    else:
        summary_value.classList.remove('over-budget')

    errors = rules.validate()
    error_box.text = ''
    if errors:
        err_list = html.UL(Class='errorlist')
        for msg in errors:
            err_list <= html.LI(msg)
        error_box <= err_list



def _wire_controls(ui_rows, summary_value, error_box):
    def refresh(ev=None):
        _update_all(ui_rows, summary_value, error_box)

    for ui in ui_rows:
        def shrink(ev, ui=ui):
            value = _read_float(ui['width']) - STEP
            _set_input(ui['width'], _clamp(value, 0.0, 2.0))
            refresh()

        def grow(ev, ui=ui):
            value = _read_float(ui['width']) + STEP
            _set_input(ui['width'], _clamp(value, 0.0, 2.0))
            refresh()

        def down(ev, ui=ui):
            value = _read_float(ui['center']) - STEP
            _set_input(ui['center'], _clamp(value, 0.0, 2.0))
            refresh()

        def up(ev, ui=ui):
            value = _read_float(ui['center']) + STEP
            _set_input(ui['center'], _clamp(value, 0.0, 2.0))
            refresh()

        ui['shrink'].bind('click', shrink)
        ui['grow'].bind('click', grow)
        ui['down'].bind('click', down)
        ui['up'].bind('click', up)
        ui['center'].bind('input', refresh)
        ui['width'].bind('input', refresh)

        def drag_start(ev, ui=ui):
            ev.preventDefault()
            bar = ui['bar']
            rect = bar.getBoundingClientRect()
            bar.classList.add('dragging')
            state = {
                'start_x': ev.clientX,
                'start_y': ev.clientY,
                'start_center': _read_float(ui['center']),
                'start_width': _read_float(ui['width']),
                'rect_width': rect.width if rect.width else 1,
            }

            def on_move(move_ev):
                dx = move_ev.clientX - state['start_x']
                dy = move_ev.clientY - state['start_y']
                unit_per_px = 2.0 / state['rect_width']
                center_delta = dx * unit_per_px
                width_delta = -dy * unit_per_px

                new_center = _clamp(state['start_center'] + center_delta, 0.0, 2.0)
                new_width = _clamp(state['start_width'] + width_delta, 0.0, 2.0)

                _set_input(ui['center'], new_center)
                _set_input(ui['width'], new_width)
                refresh()

            def on_up(up_ev):
                document.unbind('mousemove', on_move)
                document.unbind('mouseup', on_up)
                bar.classList.remove('dragging')

            document.bind('mousemove', on_move)
            document.bind('mouseup', on_up)

        ui['bar'].bind('mousedown', drag_start)


def init_habitability_form():
    form = document.select_one('form.race-form')
    if not form:
        return

    if document.body.attrs.get('data-race-builder') == '1':
        return
    document.body.attrs['data-race-builder'] = '1'

    document.body.classList.add('brython')

    table = form.select_one('table')
    if not table:
        return

    existing_error = document.select_one('.habitability-errors')
    if existing_error:
        error_box = existing_error
    else:
        error_box = html.DIV(Class='form-errors habitability-errors')

    envs = ['gravity', 'temperature', 'radiation']
    ui_rows = []

    for env in envs:
        center_input = document.getElementById(f'id_{env}_center')
        width_input = document.getElementById(f'id_{env}_width')
        if not center_input or not width_input:
            continue
        ui = _build_env_ui(env, center_input, width_input)
        if ui:
            ui_rows.append(ui)

    if not ui_rows:
        return

    existing_summary = document.select_one('.habitability-summary')
    if existing_summary:
        summary_row = existing_summary
        summary_value = summary_row.select_one('.habitability-total')
        if summary_value is None:
            summary_value = html.SPAN(Class='habitability-total')
            summary_row <= html.TD(summary_value)
    else:
        summary_row = html.TR(Class='habitability-summary')
        summary_row <= html.TH('Total Points:')
        summary_cell = html.TD()
        summary_value = html.SPAN(Class='habitability-total')
        summary_cell <= summary_value
        summary_row <= summary_cell
        summary_row <= html.TD()

    hint_cell = summary_row.getElementsByTagName('td')
    if hint_cell:
        target_cell = hint_cell[-1]
        target_cell.textContent = ''
        target_cell <= error_box
    else:
        summary_row <= html.TD(error_box)

    last_width = document.getElementById('id_radiation_width')
    if last_width and existing_summary is None:
        last_row = last_width.closest('tr')
        if last_row and last_row.parentNode:
            last_row.parentNode.insertBefore(summary_row, last_row.nextSibling)
        else:
            table <= summary_row
    elif existing_summary is None:
        table <= summary_row

    _wire_controls(ui_rows, summary_value, error_box)
    _update_all(ui_rows, summary_value, error_box)


init_habitability_form()
