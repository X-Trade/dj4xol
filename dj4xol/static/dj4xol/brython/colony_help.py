from browser import document, html, svg
from colony_rules import (
    calculate_growth_factor,
    calculate_habitability_factor,
    effective_capacity,
    calculate_staffing_ratio,
    calculate_productivity_multiplier,
    calculate_available_buildpoints,
    calculate_available_researchpoints,
    calculate_economy_percent,
    calculate_economy_factor,
    COLONISTS_PER_JOB,
    COLONISTS_PER_SHIPYARD,
)

CENTER_STEP = 0.05
WIDTH_STEP = 0.1


def _round_step(value, step):
    if step == 0:
        return value
    return round(value / step) * step


def _clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


def _log_slider_to_value(value, min_value, max_value):
    # Support zero-capable sliders by reserving 0 as an explicit zero value.
    if min_value <= 0:
        if value <= 0:
            return 0
        effective_min = 1.0
        t = (value - 1.0) / 99.0
        return effective_min * ((max_value / effective_min) ** t)
    t = value / 100.0
    return min_value * ((max_value / min_value) ** t)


def _value_to_log_slider(value, min_value, max_value):
    if min_value <= 0:
        if value <= 0:
            return 0
        effective_min = 1.0
        return int(round(
            1 + (
                math.log(value / effective_min) /
                math.log(max_value / effective_min)
            ) * 99
        ))
    if value <= 0:
        return 0
    return int(round((math.log(value / min_value) / math.log(max_value / min_value)) * 100))


def _build_env_ui(container, env, center, width):
    row = html.DIV(Class='env-row')
    label = html.SPAN(env.title(), Class='env-label')
    bar = html.DIV(Class='env-bar')
    range_marker = html.DIV(Class='env-range')
    marker = html.DIV(Class='env-marker habitable')
    bar <= range_marker
    bar <= marker
    value = html.SPAN(Class='env-value')
    row <= label
    row <= bar
    row <= value
    container <= row
    return {
        'env': env,
        'bar': bar,
        'range_marker': range_marker,
        'marker': marker,
        'value': value,
        'center': center,
        'width': width,
    }


def _apply_bar(ui):
    center = ui['center']
    width = ui['width']
    hab_min = center - width / 2
    hab_max = center + width / 2

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
    ui['value'].text = f"{center:.2f} ± {width/2:.2f}"


def _build_slider(label, min_value, max_value, step, value, on_change, log=False):
    row = html.DIV(Class='help-slider')
    row <= html.SPAN(label, Class='help-label')
    slider = html.INPUT(type='range')
    display = html.SPAN(Class='help-value')
    if log:
        slider.min = 0
        slider.max = 100
        slider.step = 1
        slider.value = _value_to_log_slider(value, min_value, max_value)
    else:
        slider.min = min_value
        slider.max = max_value
        slider.step = step
        slider.value = value
    row <= slider
    row <= display

    def update_value(ev=None):
        if log:
            actual = int(round(
                _log_slider_to_value(float(slider.value), min_value, max_value)
            ))
            display.text = f"{actual:,}"
        else:
            actual = float(slider.value)
            if step == CENTER_STEP:
                display.text = f"{actual:.2f}"
            elif step == WIDTH_STEP:
                display.text = f"{actual:.1f}"
            else:
                display.text = f"{actual:,.0f}"
        on_change(actual)

    slider.bind('input', update_value)
    update_value()
    return row


def init():
    if document.body.attrs.get('data-colony-help') == '1':
        return
    document.body.attrs['data-colony-help'] = '1'

    race_container = document.getElementById('race-ranges')
    planet_container = document.getElementById('planet-env')
    pop_container = document.getElementById('population-slider')
    infra_container = document.getElementById('infra-sliders')
    results_container = document.getElementById('colony-results')

    if not race_container:
        return

    race_container.text = ''
    planet_container.text = ''
    pop_container.text = ''
    infra_container.text = ''
    results_container.text = ''

    state = {
        'centers': {'gravity': 1.0, 'temperature': 1.0, 'radiation': 1.0},
        'widths': {'gravity': 1.0, 'temperature': 1.0, 'radiation': 1.0},
        'planet': {'gravity': 1.0, 'temperature': 1.0, 'radiation': 1.0},
        'population': 1000000,
        'mines': 10,
        'factories': 10,
        'labs': 10,
        'defenses': 0,
        'shipyards': 0,
    }

    race_rows = []
    for env in ['gravity', 'temperature', 'radiation']:
        race_rows.append(_build_env_ui(race_container, env, state['centers'][env], state['widths'][env]))

    planet_rows = []
    for env in ['gravity', 'temperature', 'radiation']:
        planet_rows.append(_build_env_ui(planet_container, env, state['planet'][env], 0.0))

    def refresh():
        # Clamp centers if width pushes range out of bounds
        for env in ['gravity', 'temperature', 'radiation']:
            width = _round_step(state['widths'][env], WIDTH_STEP)
            min_center = width / 2
            max_center = 2.0 - width / 2
            center = _round_step(state['centers'][env], CENTER_STEP)
            center = _clamp(center, min_center, max_center)
            state['widths'][env] = width
            state['centers'][env] = center
        for ui in race_rows:
            ui['center'] = state['centers'][ui['env']]
            ui['width'] = state['widths'][ui['env']]
            _apply_bar(ui)
        for ui in planet_rows:
            ui['center'] = state['planet'][ui['env']]
            ui['width'] = 0.0
            _apply_bar(ui)
            env = ui['env']
            hab_min = state['centers'][env] - state['widths'][env] / 2
            hab_max = state['centers'][env] + state['widths'][env] / 2
            if hab_min <= state['planet'][env] <= hab_max:
                ui['marker'].classList.add('habitable')
                ui['marker'].classList.remove('uninhabitable')
            else:
                ui['marker'].classList.add('uninhabitable')
                ui['marker'].classList.remove('habitable')

        class Dummy:
            pass

        star = Dummy()
        star.gravity = state['planet']['gravity']
        star.temperature = state['planet']['temperature']
        star.radiation = state['planet']['radiation']
        star.colonists = int(state['population'])
        star.mines = int(state['mines'])
        star.factories = int(state['factories'])
        star.labs = int(state['labs'])
        star.defenses = int(state['defenses'])
        star.shipyards = int(state['shipyards'])
        star.buildpoints_consumed = int(state['factories'] * 10)
        star.base_capacity = 10000

        player = Dummy()
        player.gravity_center = state['centers']['gravity']
        player.temperature_center = state['centers']['temperature']
        player.radiation_center = state['centers']['radiation']
        player.gravity_width = state['widths']['gravity']
        player.temperature_width = state['widths']['temperature']
        player.radiation_width = state['widths']['radiation']

        def hab_min(env):
            return getattr(player, f"{env}_center") - getattr(player, f"{env}_width") / 2

        def hab_max(env):
            return getattr(player, f"{env}_center") + getattr(player, f"{env}_width") / 2

        player.hab_min = hab_min
        player.hab_max = hab_max

        growth = calculate_growth_factor(player, star)
        capacity = effective_capacity(player, star)
        staffing = calculate_staffing_ratio(star)
        productivity = calculate_productivity_multiplier(staffing)
        economy = calculate_economy_percent(star)
        bp = calculate_available_buildpoints(star)
        rp = calculate_available_researchpoints(star)
        hab = calculate_habitability_factor(player, star)
        jobs = (
            (star.mines + star.factories + star.labs + star.defenses) *
            COLONISTS_PER_JOB
            + star.shipyards * COLONISTS_PER_SHIPYARD
        )

        table = html.TABLE(Class='help-results-table')

        def add_result(label, value):
            row = html.TR()
            row <= html.TH(label, Class='env-label')
            row <= html.TD(value, Class='detail-value')
            table <= row

        def proj(years):
            pop = star.colonists
            for _ in range(years):
                pop = int(pop + pop * growth)
                if pop < 0:
                    pop = 0
                    break
            return pop

        results_container.text = ''
        add_result("Habitability", f"{hab:.3f}")
        add_result("Capacity", f"{capacity:,}")
        if capacity > 0:
            add_result("Pop/Capacity", f"{(star.colonists / float(capacity)) * 100:.1f}%")
        add_result("Jobs", f"{jobs:,}")
        add_result("Employment", f"{staffing * 100:.1f}%")
        add_result("Productivity", f"{productivity * 100:.1f}%")
        add_result("Economy", f"{economy:.1f}%")
        add_result("Buildpoints/Turn", f"{bp:,}")
        add_result("Research/Turn", f"{rp:,}")
        add_result("Growth/Turn", f"{growth * 100:.2f}%")
        add_result("Pop (1y)", f"{proj(1):,}")
        add_result("Pop (10y)", f"{proj(10):,}")
        add_result("Pop (50y)", f"{proj(50):,}")
        add_result("Pop (100y)", f"{proj(100):,}")
        results_container <= table

        # Simple projection graph (0-100 years)
        years = list(range(0, 101, 5))
        pops = []
        pop = star.colonists
        for y in years:
            if y == 0:
                pops.append(pop)
                continue
            for _ in range(5):
                pop = int(pop + pop * growth)
                if pop < 0:
                    pop = 0
                    break
            pops.append(pop)

        max_pop = max(pops) if pops else 1
        width = 360
        height = 120
        svg_el = svg.svg(width=width, height=height, Class='growth-graph')
        points = []
        for i, val in enumerate(pops):
            x = int(i / (len(pops) - 1) * (width - 20)) + 10
            y = height - 10 - int((val / max_pop) * (height - 20))
            points.append(f"{x},{y}")
        polyline = svg.polyline()
        polyline.attrs['points'] = " ".join(points)
        polyline.attrs['fill'] = "none"
        polyline.attrs['stroke'] = "currentColor"
        polyline.attrs['stroke-width'] = "2"
        svg_el <= polyline
        results_container <= svg_el

    def set_center(env, value):
        state['centers'][env] = _round_step(value, CENTER_STEP)
        refresh()

    def set_width(env, value):
        state['widths'][env] = _round_step(value, WIDTH_STEP)
        refresh()

    def set_planet(env, value):
        state['planet'][env] = _round_step(value, CENTER_STEP)
        refresh()

    def bind_drag(ui):
        def drag_start(ev, ui=ui):
            ev.preventDefault()
            bar = ui['bar']
            rect = bar.getBoundingClientRect()
            bar.classList.add('dragging')
            state_drag = {
                'start_x': ev.clientX,
                'start_y': ev.clientY,
                'start_center': state['centers'][ui['env']],
                'start_width': state['widths'][ui['env']],
                'rect_width': rect.width if rect.width else 1,
            }

            def on_move(move_ev):
                dx = move_ev.clientX - state_drag['start_x']
                dy = move_ev.clientY - state_drag['start_y']
                unit_per_px = 2.0 / state_drag['rect_width']
                center_delta = dx * unit_per_px
                width_delta = -dy * unit_per_px

                new_center = state_drag['start_center'] + center_delta
                new_width = state_drag['start_width'] + width_delta
                new_width = _clamp(new_width, 0.1, 2.0)
                min_center = new_width / 2
                max_center = 2.0 - new_width / 2
                new_center = _clamp(new_center, min_center, max_center)

                state['centers'][ui['env']] = _round_step(new_center, CENTER_STEP)
                state['widths'][ui['env']] = _round_step(new_width, WIDTH_STEP)
                refresh()

            def on_up(up_ev):
                document.unbind('mousemove', on_move)
                document.unbind('mouseup', on_up)
                bar.classList.remove('dragging')

            document.bind('mousemove', on_move)
            document.bind('mouseup', on_up)

        ui['bar'].bind('mousedown', drag_start)

    for ui in race_rows:
        bind_drag(ui)

    def bind_planet_drag(ui):
        def drag_start(ev, ui=ui):
            ev.preventDefault()
            bar = ui['bar']
            rect = bar.getBoundingClientRect()
            bar.classList.add('dragging')
            state_drag = {
                'start_x': ev.clientX,
                'start_center': state['planet'][ui['env']],
                'rect_width': rect.width if rect.width else 1,
            }

            def on_move(move_ev):
                dx = move_ev.clientX - state_drag['start_x']
                unit_per_px = 2.0 / state_drag['rect_width']
                center_delta = dx * unit_per_px
                new_center = state_drag['start_center'] + center_delta
                new_center = _clamp(new_center, 0.0, 2.0)
                state['planet'][ui['env']] = _round_step(new_center, CENTER_STEP)
                refresh()

            def on_up(up_ev):
                document.unbind('mousemove', on_move)
                document.unbind('mouseup', on_up)
                bar.classList.remove('dragging')

            document.bind('mousemove', on_move)
            document.bind('mouseup', on_up)

        ui['bar'].bind('mousedown', drag_start)

    for ui in planet_rows:
        bind_planet_drag(ui)

    pop_container <= _build_slider(
        "Population", 1_000, 50_000_000_000, 1, state['population'],
        lambda v: state.update({'population': v}) or refresh(), log=True
    )

    def set_infra(key, value):
        state[key] = value
        refresh()

    infra_container <= _build_slider("Mines", 0, 2000, 1, state['mines'], lambda v: set_infra('mines', v), log=True)
    infra_container <= _build_slider("Factories", 0, 2000, 1, state['factories'], lambda v: set_infra('factories', v), log=True)
    infra_container <= _build_slider("Labs", 0, 2000, 1, state['labs'], lambda v: set_infra('labs', v), log=True)
    infra_container <= _build_slider("Defenses", 0, 2000, 1, state['defenses'], lambda v: set_infra('defenses', v), log=True)
    infra_container <= _build_slider("Shipyards", 0, 200, 1, state['shipyards'], lambda v: set_infra('shipyards', v), log=True)

    refresh()


import math
init()
