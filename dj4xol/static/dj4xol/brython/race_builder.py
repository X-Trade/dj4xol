from browser import document, html
import json
from habitability_rules import RaceCreationRules

STEP = 0.1
CENTER_STEP = 0.05
WIDTH_STEP = 0.1
FIXED_HOMEWORLD_HINT = None


def _round_step(value, step):
    if step == 0:
        return value
    return round(value / step) * step


def _clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


def _read_float(input_el):
    try:
        return float(input_el.value)
    except (TypeError, ValueError):
        return 0.0


def _set_input(input_el, value, step):
    decimals = 2 if step == 0.05 else 1
    input_el.value = f"{_round_step(value, step):.{decimals}f}"


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
    starting_input = document.getElementById('id_starting_colonists')
    starting_colonists = 0
    if starting_input:
        try:
            starting_colonists = int(starting_input.value or 0)
        except ValueError:
            starting_colonists = 0

    def read_int(field_id, default=0):
        el = document.getElementById(field_id)
        if not el:
            return default
        try:
            return int(el.value or 0)
        except ValueError:
            return default

    starting_mines = read_int('id_starting_mines', 4)
    starting_factories = read_int('id_starting_factories', 2)
    starting_labs = read_int('id_starting_labs', 1)
    starting_shipyards = read_int('id_starting_shipyards', 1)
    starting_fleets = read_int('id_starting_fleets', 2)
    starting_tech_level = read_int('id_starting_tech_level', 3)
    starting_tech_level_costs = {}
    starting_tech_cost_json = document.getElementById('starting-tech-costs-json')
    if starting_tech_cost_json:
        try:
            starting_tech_level_costs = {
                int(k): float(v) for (k, v) in json.loads(
                    starting_tech_cost_json.textContent or '{}'
                ).items()
            }
        except Exception:
            starting_tech_level_costs = {}
    max_defined_start_level = max(starting_tech_level_costs.keys()) if starting_tech_level_costs else 0
    if max_defined_start_level > 0:
        starting_tech_level = _clamp(starting_tech_level, 0, max_defined_start_level)
        starting_tech_input = document.getElementById('id_starting_tech_level')
        if starting_tech_input:
            starting_tech_input.value = str(int(starting_tech_level))
    starting_tech_level_cost = float(
        starting_tech_level_costs.get(int(starting_tech_level), 0.0)
    )
    starting_tech_warning = document.getElementById('starting-tech-warning')
    if starting_tech_warning:
        if int(starting_tech_level) > 5:
            starting_tech_warning.style.display = 'block'
        else:
            starting_tech_warning.style.display = 'none'
    convert_checkbox = document.getElementById('id_convert_unused_buildpoints_to_research')
    singular_checkbox = document.getElementById('id_singular_research')
    fixed_homeworld_checkbox = document.getElementById('id_fixed_homeworld')
    convert_unused_buildpoints_to_research = bool(
        convert_checkbox and convert_checkbox.checked
    )
    singular_research = bool(singular_checkbox and singular_checkbox.checked)
    fixed_homeworld = bool(fixed_homeworld_checkbox and fixed_homeworld_checkbox.checked)
    if FIXED_HOMEWORLD_HINT is not None:
        FIXED_HOMEWORLD_HINT.style.display = 'block' if fixed_homeworld else 'none'
    for ui in ui_rows:
        env = ui['env']
        widths[env] = _clamp(widths[env], 0.1, 2.0)
        min_center = widths[env] / 2.0
        max_center = 2.0 - widths[env] / 2.0
        centers[env] = _clamp(centers[env], min_center, max_center)
        _set_input(ui['width'], widths[env], WIDTH_STEP)
        _set_input(ui['center'], centers[env], CENTER_STEP)
    rules = RaceCreationRules(
        centers,
        widths,
        starting_colonists=starting_colonists,
        starting_mines=starting_mines,
        starting_factories=starting_factories,
        starting_labs=starting_labs,
        starting_shipyards=starting_shipyards,
        starting_fleets=starting_fleets,
        starting_tech_level=starting_tech_level,
        starting_tech_level_cost=starting_tech_level_cost,
        convert_unused_buildpoints_to_research=convert_unused_buildpoints_to_research,
        singular_research=singular_research,
        fixed_homeworld=fixed_homeworld,
    )

    for ui in ui_rows:
        _apply_bar(ui, rules)
        points = rules.per_env_cost(ui['env'])
        ui['points'].text = f"{points:.2f} pts"
        ui['range'].text = f"Range {rules.hab_min(ui['env']):.1f}–{rules.hab_max(ui['env']):.1f}"
        ui['width_value'].text = f"{rules.widths[ui['env']]:.2f}"
        ui['center_value'].text = f"{rules.centers[ui['env']]:.2f}"

    total = rules.total_cost()
    summary_value.text = f"{total:.2f}"
    summary_value.attrs['data-budget'] = f"{rules.budget:.1f} pts"
    if total > rules.budget:
        summary_value.classList.add('over-budget')
        summary_value.classList.remove('under-budget')
    else:
        summary_value.classList.remove('over-budget')
        summary_value.classList.add('under-budget')

    errors = rules.validate()
    error_box.text = ''
    if errors:
        err_list = html.UL(Class='errorlist')
        for msg in errors:
            err_list <= html.LI(msg)
        error_box <= err_list

    def set_points(row_id, value):
        row = document.select_one(f'tr[data-{row_id}=\"1\"]')
        if row:
            points_target = row.select_one(f'.{row_id}-points')
            if points_target:
                points_target.text = f"{value:.2f} pts"

    set_points('colonist-row', rules.colonist_cost())
    set_points('mine-row', rules.mines_cost())
    set_points('factory-row', rules.factories_cost())
    set_points('lab-row', rules.labs_cost())
    set_points('shipyard-row', rules.shipyards_cost())
    set_points('fleet-row', rules.fleets_cost())
    set_points('starting-tech-row', rules.starting_tech_level_cost())
    set_points('convert-bp-row', rules.convert_unused_buildpoints_cost())
    set_points('singular-row', -rules.singular_research_savings())
    set_points('fixed-homeworld-row', -rules.fixed_homeworld_savings())



def _wire_controls(ui_rows, summary_value, error_box):
    def refresh(ev=None):
        _update_all(ui_rows, summary_value, error_box)

    def _event_point(ev):
        touch = None
        if hasattr(ev, 'touches') and ev.touches:
            touch = ev.touches[0]
        elif hasattr(ev, 'changedTouches') and ev.changedTouches:
            touch = ev.changedTouches[0]
        if touch:
            return touch.clientX, touch.clientY
        return ev.clientX, ev.clientY

    for ui in ui_rows:
        def shrink(ev, ui=ui):
            value = _read_float(ui['width']) - WIDTH_STEP
            _set_input(ui['width'], _clamp(value, 0.1, 2.0), WIDTH_STEP)
            refresh()

        def grow(ev, ui=ui):
            value = _read_float(ui['width']) + WIDTH_STEP
            _set_input(ui['width'], _clamp(value, 0.1, 2.0), WIDTH_STEP)
            refresh()

        def down(ev, ui=ui):
            value = _read_float(ui['center']) - CENTER_STEP
            _set_input(ui['center'], _clamp(value, 0.0, 2.0), CENTER_STEP)
            refresh()

        def up(ev, ui=ui):
            value = _read_float(ui['center']) + CENTER_STEP
            _set_input(ui['center'], _clamp(value, 0.0, 2.0), CENTER_STEP)
            refresh()

        ui['shrink'].bind('click', shrink)
        ui['grow'].bind('click', grow)
        ui['down'].bind('click', down)
        ui['up'].bind('click', up)
        ui['center'].bind('input', refresh)
        ui['width'].bind('input', refresh)

        def _start_drag(ev, ui=ui, is_touch=False):
            ev.preventDefault()
            bar = ui['bar']
            rect = bar.getBoundingClientRect()
            bar.classList.add('dragging')
            start_x, start_y = _event_point(ev)
            state = {
                'start_x': start_x,
                'start_y': start_y,
                'start_center': _read_float(ui['center']),
                'start_width': _read_float(ui['width']),
                'rect_width': rect.width if rect.width else 1,
            }

            def on_move(move_ev):
                move_ev.preventDefault()
                move_x, move_y = _event_point(move_ev)
                dx = move_x - state['start_x']
                dy = move_y - state['start_y']
                unit_per_px = 2.0 / state['rect_width']
                center_delta = dx * unit_per_px
                width_delta = -dy * unit_per_px

                new_center = _clamp(state['start_center'] + center_delta, 0.0, 2.0)
                new_width = _clamp(state['start_width'] + width_delta, 0.1, 2.0)

                _set_input(ui['center'], new_center, CENTER_STEP)
                _set_input(ui['width'], new_width, WIDTH_STEP)
                refresh()

            def on_up(up_ev):
                if is_touch:
                    document.unbind('touchmove', on_move)
                    document.unbind('touchend', on_up)
                else:
                    document.unbind('mousemove', on_move)
                    document.unbind('mouseup', on_up)
                bar.classList.remove('dragging')

            if is_touch:
                document.bind('touchmove', on_move)
                document.bind('touchend', on_up)
            else:
                document.bind('mousemove', on_move)
                document.bind('mouseup', on_up)

        def drag_start(ev, ui=ui):
            _start_drag(ev, ui=ui, is_touch=False)

        def drag_start_touch(ev, ui=ui):
            _start_drag(ev, ui=ui, is_touch=True)

        ui['bar'].bind('mousedown', drag_start)
        ui['bar'].bind('touchstart', drag_start_touch)


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

    def attach_points(field_id, row_attr, points_class):
        input_el = document.getElementById(field_id)
        if not input_el:
            return None
        row = input_el.closest('tr')
        if not row:
            return None
        cells = row.getElementsByTagName('td')
        if len(cells) < 2:
            return row
        hint_cell = cells[1]
        hint_text = hint_cell.textContent
        hint_cell.textContent = ''
        points = html.DIV(Class=f'habitability-points {points_class}')
        hint_cell <= points
        if row_attr == 'fixed-homeworld-row' and hint_text:
            hint_text = hint_text.strip()
            if hint_text.lower().startswith('-16 points'):
                dot = hint_text.find('.')
                if dot != -1:
                    hint_text = hint_text[dot + 1:].strip()
                else:
                    hint_text = hint_text[len('-16 points'):].strip()
            global FIXED_HOMEWORLD_HINT
            FIXED_HOMEWORLD_HINT = html.DIV(hint_text, Class='fixed-homeworld-hint')
            FIXED_HOMEWORLD_HINT.style.display = 'none'
            hint_cell <= FIXED_HOMEWORLD_HINT
        row.attrs[f'data-{row_attr}'] = '1'
        return row

    starting_input = document.getElementById('id_starting_colonists')
    attach_points('id_starting_colonists', 'colonist-row', 'colonist-row-points')
    attach_points('id_starting_mines', 'mine-row', 'mine-row-points')
    attach_points('id_starting_factories', 'factory-row', 'factory-row-points')
    attach_points('id_starting_labs', 'lab-row', 'lab-row-points')
    attach_points('id_starting_shipyards', 'shipyard-row', 'shipyard-row-points')
    attach_points('id_starting_fleets', 'fleet-row', 'fleet-row-points')
    attach_points('id_starting_tech_level', 'starting-tech-row', 'starting-tech-row-points')
    attach_points(
        'id_convert_unused_buildpoints_to_research',
        'convert-bp-row',
        'convert-bp-row-points',
    )
    attach_points('id_singular_research', 'singular-row', 'singular-row-points')
    attach_points('id_fixed_homeworld', 'fixed-homeworld-row', 'fixed-homeworld-row-points')
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

    leftover_checkbox = document.getElementById('id_spend_leftover_on_minerals')
    leftover_research_checkbox = document.getElementById('id_spend_leftover_on_research')
    if existing_summary is None and leftover_checkbox:
        leftover_row = leftover_checkbox.closest('tr')
        if leftover_row and leftover_row.parentNode:
            leftover_row.parentNode.insertBefore(summary_row, leftover_row)
        else:
            table <= summary_row
    elif existing_summary is None:
        last_width = document.getElementById('id_radiation_width')
        if last_width:
            last_row = last_width.closest('tr')
            if last_row and last_row.parentNode:
                last_row.parentNode.insertBefore(summary_row, last_row.nextSibling)
            else:
                table <= summary_row
        else:
            table <= summary_row

    _wire_controls(ui_rows, summary_value, error_box)
    for field_id in [
        'id_starting_colonists',
        'id_starting_mines',
        'id_starting_factories',
        'id_starting_labs',
        'id_starting_shipyards',
        'id_starting_fleets',
        'id_starting_tech_level',
    ]:
        input_el = document.getElementById(field_id)
        if input_el:
            input_el.bind('input', lambda ev: _update_all(ui_rows, summary_value, error_box))
    for field_id in ['id_convert_unused_buildpoints_to_research', 'id_singular_research', 'id_fixed_homeworld']:
        checkbox = document.getElementById(field_id)
        if checkbox:
            checkbox.bind('change', lambda ev: _update_all(ui_rows, summary_value, error_box))

    def _sync_leftover_options(ev=None):
        if not leftover_checkbox or not leftover_research_checkbox:
            return
        if leftover_checkbox.checked:
            leftover_research_checkbox.checked = False
            leftover_research_checkbox.disabled = True
            leftover_checkbox.disabled = False
        elif leftover_research_checkbox.checked:
            leftover_checkbox.checked = False
            leftover_checkbox.disabled = True
            leftover_research_checkbox.disabled = False
        else:
            leftover_checkbox.disabled = False
            leftover_research_checkbox.disabled = False

    if leftover_checkbox and leftover_research_checkbox:
        leftover_checkbox.bind('change', _sync_leftover_options)
        leftover_research_checkbox.bind('change', _sync_leftover_options)
        _sync_leftover_options()

    _update_all(ui_rows, summary_value, error_box)


init_habitability_form()
