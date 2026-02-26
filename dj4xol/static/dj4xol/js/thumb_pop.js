(function() {
    var HOLD_MS = 350;
    var targets = document.querySelectorAll('.thumb-pop-target');
    if (!targets.length) return;

    var states = new WeakMap();
    var active = [];

    function getState(el) {
        var state = states.get(el);
        if (!state) {
            state = { isDown: false, timerId: null, active: false };
            states.set(el, state);
        }
        return state;
    }

    function clearTimer(state) {
        if (state.timerId) {
            clearTimeout(state.timerId);
            state.timerId = null;
        }
    }

    function clamp(val, min, max) {
        return Math.max(min, Math.min(max, val));
    }

    function showOverlay(el) {
        var state = getState(el);
        if (state.overlayEl) return;

        var rect = el.getBoundingClientRect();
        var width = rect.width * 2;
        var height = rect.height * 2;
        var left = rect.left - (width - rect.width) / 2;
        var top = rect.top - (height - rect.height) / 2;
        left = clamp(left, 6, Math.max(6, window.innerWidth - width - 6));
        top = clamp(top, 6, Math.max(6, window.innerHeight - height - 6));

        var overlay = el.cloneNode(true);
        overlay.classList.add('thumb-pop-overlay');
        overlay.style.left = left + 'px';
        overlay.style.top = top + 'px';
        overlay.style.width = width + 'px';
        overlay.style.height = height + 'px';
        document.body.appendChild(overlay);
        state.overlayEl = overlay;
    }

    function hideOverlay(el) {
        var state = getState(el);
        if (!state.overlayEl) return;
        if (state.overlayEl.parentNode) {
            state.overlayEl.parentNode.removeChild(state.overlayEl);
        }
        state.overlayEl = null;
    }

    function begin(el) {
        var state = getState(el);
        state.isDown = true;
        clearTimer(state);
        state.timerId = setTimeout(function() {
            if (!state.isDown) return;
            state.active = true;
            showOverlay(el);
        }, HOLD_MS);
        if (active.indexOf(el) === -1) {
            active.push(el);
        }
    }

    function end(el) {
        var state = getState(el);
        if (!state.isDown && !state.active) return;
        state.isDown = false;
        clearTimer(state);
        state.active = false;
        hideOverlay(el);
    }

    function endAll() {
        for (var i = 0; i < active.length; i += 1) {
            end(active[i]);
        }
        active = [];
    }

    targets.forEach(function(el) {
        el.addEventListener('mousedown', function() { begin(el); });
        el.addEventListener('touchstart', function() { begin(el); }, { passive: true });
        el.addEventListener('dragstart', function(ev) { ev.preventDefault(); });
    });

    document.addEventListener('mouseup', endAll);
    document.addEventListener('touchend', endAll);
    document.addEventListener('touchcancel', endAll);
    window.addEventListener('blur', endAll);
})();
