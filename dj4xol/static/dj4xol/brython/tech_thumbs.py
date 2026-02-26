from browser import document, timer, window

HOLD_MS = 350
LONG_HOLD_MS = 2000
CYCLE_MS = 2000
BODY = document.select_one('body')


class ThumbPopController:
    def __init__(self, img):
        self.img = img
        self.wrap = img.parent
        self.is_down = False
        self.down_started_ms = 0
        self.hold_timer_id = None
        self.cycle_timer_id = None
        self.pop_clone = None
        self.img.style.cursor = 'zoom-in'
        self.icons = self._read_icons()
        self.idx = self._read_initial_index()
        self.img.attrs['src'] = self.icons[self.idx]
        self.img.attrs['data-index'] = str(self.idx)

    def _read_icons(self):
        raw = str(self.img.attrs.get('data-icons', '') or '')
        if raw:
            icons = [part for part in raw.split('|') if part]
            if icons:
                return icons
        return [str(self.img.attrs.get('src', '') or '')]

    def _read_initial_index(self):
        try:
            idx = int(str(self.img.attrs.get('data-index', '0')))
        except (TypeError, ValueError):
            idx = 0
        if idx < 0:
            idx = 0
        return idx % len(self.icons)

    def clear_hold_timer(self):
        if self.hold_timer_id is not None:
            timer.clear_timeout(self.hold_timer_id)
            self.hold_timer_id = None

    def clear_cycle_timer(self):
        if self.cycle_timer_id is not None:
            timer.clear_timeout(self.cycle_timer_id)
            self.cycle_timer_id = None

    def schedule_cycle(self):
        if len(self.icons) <= 1:
            return
        self.clear_cycle_timer()
        self.cycle_timer_id = timer.set_timeout(self.on_cycle_tick, CYCLE_MS)

    def advance_icon(self):
        if len(self.icons) <= 1:
            return
        self.idx = (self.idx + 1) % len(self.icons)
        self.img.attrs['src'] = self.icons[self.idx]
        self.img.attrs['data-index'] = str(self.idx)

    def on_cycle_tick(self):
        self.cycle_timer_id = None
        if self.is_down:
            return
        self.advance_icon()
        self.schedule_cycle()

    def hide_pop(self):
        if self.pop_clone is not None:
            try:
                self.pop_clone.remove()
            except Exception:
                pass
            self.pop_clone = None

    def show_pop(self):
        if self.pop_clone is not None or self.wrap is None:
            return

        rect = self.wrap.getBoundingClientRect()
        rect_width = float(rect.width)
        rect_height = float(rect.height)
        rect_left = float(rect.left)
        rect_top = float(rect.top)
        viewport_w = float(window.innerWidth)
        viewport_h = float(window.innerHeight)

        width = rect_width * 2.0
        height = rect_height * 2.0
        left = rect_left - ((width - rect_width) / 2.0)
        top = rect_top - ((height - rect_height) / 2.0)

        max_left = max(6.0, viewport_w - width - 6.0)
        max_top = max(6.0, viewport_h - height - 6.0)
        left = max(6.0, min(left, max_left))
        top = max(6.0, min(top, max_top))

        self.pop_clone = self.wrap.cloneNode(True)
        self.pop_clone.class_name = (
            f'{self.pop_clone.class_name} thumb-pop-overlay'
        ).strip()
        self.pop_clone.style.left = f'{left}px'
        self.pop_clone.style.top = f'{top}px'
        self.pop_clone.style.width = f'{width}px'
        self.pop_clone.style.height = f'{height}px'
        # Inline critical layout styles so placement doesn't depend on CSS load/order.
        self.pop_clone.style.position = 'fixed'
        self.pop_clone.style.zIndex = '9999'
        self.pop_clone.style.pointerEvents = 'none'
        self.pop_clone.style.margin = '0'
        self.pop_clone.style.transform = 'none'
        if BODY is not None:
            BODY <= self.pop_clone
        else:
            document <= self.pop_clone

    def on_mouse_down(self, _ev):
        self.is_down = True
        self.down_started_ms = int(window.Date.new().getTime())
        self.clear_hold_timer()
        self.clear_cycle_timer()
        self.hide_pop()
        self.hold_timer_id = timer.set_timeout(self.show_pop, HOLD_MS)

    def on_mouse_up(self, _ev):
        if not self.is_down:
            return
        held_ms = max(0, int(window.Date.new().getTime()) - self.down_started_ms)
        self.is_down = False
        self.down_started_ms = 0
        self.clear_hold_timer()
        self.hide_pop()
        if held_ms < LONG_HOLD_MS:
            self.advance_icon()
        self.schedule_cycle()

    def bind(self):
        self.img.bind('mousedown', self.on_mouse_down)
        self.img.bind('touchstart', self.on_mouse_down)
        document.bind('mouseup', self.on_mouse_up)
        document.bind('touchend', self.on_mouse_up)
        document.bind('touchcancel', self.on_mouse_up)
        self.schedule_cycle()


def init():
    imgs = document.select('.tech-thumb')
    for img in imgs:
        ThumbPopController(img).bind()


print('tech_thumbs Brython init')
init()
