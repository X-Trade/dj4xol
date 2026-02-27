(function() {
    function updateCustomPanelScrollbar(el) {
        if (!el) return;
        var overlay = el.__customScrollbarOverlay;
        if (!overlay) return;
        var thumb = overlay.__thumbEl;
        if (!thumb) return;

        var clientHeight = el.clientHeight;
        var scrollHeight = el.scrollHeight;
        if (clientHeight <= 0) return;

        var computed = window.getComputedStyle(el);
        var thumbScale = parseFloat(computed.getPropertyValue('--panel-scroll-thumb-scale'));
        var thumbMin = parseFloat(computed.getPropertyValue('--panel-scroll-thumb-min-size'));
        if (!isFinite(thumbScale) || thumbScale <= 0) thumbScale = 0.5;
        if (!isFinite(thumbMin) || thumbMin <= 0) thumbMin = 12;

        var thumbSize;
        var thumbTop;
        var thumbOpacity;
        var maxTop;

        if (scrollHeight <= clientHeight + 1) {
            thumbSize = Math.max(20, Math.min(clientHeight, Math.round(clientHeight * 0.35)));
            thumbSize = Math.max(thumbMin, Math.round(thumbSize * thumbScale));
            thumbSize = Math.min(thumbSize, clientHeight);
            maxTop = Math.max(0, clientHeight - thumbSize);
            thumbTop = Math.round(maxTop / 2);
            thumbOpacity = 0;
        } else {
            var ratio = clientHeight / scrollHeight;
            thumbSize = Math.max(20, Math.round(clientHeight * ratio));
            thumbSize = Math.max(thumbMin, Math.round(thumbSize * thumbScale));
            thumbSize = Math.min(thumbSize, clientHeight);
            maxTop = Math.max(0, clientHeight - thumbSize);
            thumbTop = Math.round((el.scrollTop / (scrollHeight - clientHeight)) * maxTop);
            thumbOpacity = 1;
        }

        thumbTop = Math.max(0, Math.min(thumbTop, Math.max(0, clientHeight - thumbSize)));

        overlay.style.top = el.offsetTop + 'px';
        overlay.style.right = '0px';
        overlay.style.height = clientHeight + 'px';
        thumb.style.height = thumbSize + 'px';
        thumb.style.transform = 'translateY(' + thumbTop + 'px)';
        thumb.style.opacity = String(thumbOpacity);

        el.__customScrollbarMetrics = {
            clientHeight: clientHeight,
            scrollHeight: scrollHeight,
            thumbSize: thumbSize,
            maxTop: maxTop
        };
    }

    function ensureCustomScrollbarOverlay(el) {
        if (!el || el.__customScrollbarOverlay) {
            return el ? el.__customScrollbarOverlay : null;
        }

        var parent = el.parentElement;
        if (!parent) return null;

        var computedPos = window.getComputedStyle(parent).position;
        if (!computedPos || computedPos === 'static') {
            parent.style.position = 'relative';
        }

        var overlay = document.createElement('span');
        overlay.className = 'panel-scrollbar-overlay';
        var track = document.createElement('span');
        track.className = 'panel-scrollbar-track';
        var thumb = document.createElement('span');
        thumb.className = 'panel-scrollbar-thumb';
        overlay.appendChild(track);
        overlay.appendChild(thumb);
        parent.appendChild(overlay);

        el.__customScrollbarOverlay = overlay;
        overlay.__trackEl = track;
        overlay.__thumbEl = thumb;

        overlay.addEventListener('pointerdown', function(ev) {
            if (ev.target === thumb) return;
            var metrics = el.__customScrollbarMetrics;
            if (!metrics || metrics.scrollHeight <= metrics.clientHeight || metrics.maxTop <= 0) return;
            var rect = overlay.getBoundingClientRect();
            var y = ev.clientY - rect.top;
            var targetTop = y - (metrics.thumbSize / 2);
            targetTop = Math.max(0, Math.min(targetTop, metrics.maxTop));
            el.scrollTop = (targetTop / metrics.maxTop) * (metrics.scrollHeight - metrics.clientHeight);
            updateCustomPanelScrollbar(el);
        });

        thumb.addEventListener('pointerdown', function(ev) {
            ev.preventDefault();
            var startY = ev.clientY;
            var startScrollTop = el.scrollTop;
            var metrics = el.__customScrollbarMetrics;
            if (!metrics || metrics.maxTop <= 0 || metrics.scrollHeight <= metrics.clientHeight) return;
            var pxToScroll = (metrics.scrollHeight - metrics.clientHeight) / metrics.maxTop;

            try {
                thumb.setPointerCapture(ev.pointerId);
            } catch (err) {}

            function onMove(moveEv) {
                var dy = moveEv.clientY - startY;
                el.scrollTop = startScrollTop + (dy * pxToScroll);
                updateCustomPanelScrollbar(el);
            }

            function onEnd(endEv) {
                document.removeEventListener('pointermove', onMove);
                document.removeEventListener('pointerup', onEnd);
                document.removeEventListener('pointercancel', onEnd);
                try {
                    thumb.releasePointerCapture(endEv.pointerId);
                } catch (err) {}
            }

            document.addEventListener('pointermove', onMove);
            document.addEventListener('pointerup', onEnd);
            document.addEventListener('pointercancel', onEnd);
        });

        overlay.addEventListener('wheel', function(ev) {
            ev.preventDefault();
            el.scrollTop += ev.deltaY;
            updateCustomPanelScrollbar(el);
        }, { passive: false });

        return overlay;
    }

    function refreshCustomPanelScrollbars() {
        if (!document.body.classList.contains('lcars') &&
            !document.body.classList.contains('win95')) {
            return;
        }

        var scrollEls = document.querySelectorAll('.panel-scrollable-list, .panel-scrollable-text');
        for (var i = 0; i < scrollEls.length; i += 1) {
            var el = scrollEls[i];
            if (!el.__customScrollbarBound) {
                el.__customScrollbarBound = true;
                el.addEventListener('scroll', function(ev) {
                    updateCustomPanelScrollbar(ev.currentTarget);
                });
            }
            ensureCustomScrollbarOverlay(el);
            updateCustomPanelScrollbar(el);
        }
    }

    window.dj4xolRefreshPanelScrollbars = refreshCustomPanelScrollbars;

    document.addEventListener('DOMContentLoaded', function() {
        refreshCustomPanelScrollbars();
        setTimeout(refreshCustomPanelScrollbars, 0);
    });
    document.addEventListener('click', function(ev) {
        var header = ev.target && ev.target.closest ? ev.target.closest('.panel > h2') : null;
        if (!header) return;
        setTimeout(refreshCustomPanelScrollbars, 260);
    });
    window.addEventListener('resize', refreshCustomPanelScrollbars);
})();
