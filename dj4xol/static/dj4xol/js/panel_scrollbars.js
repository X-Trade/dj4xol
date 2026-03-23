(function() {
    function useCustomThemeScrollbars() {
        return document.body.classList.contains('lcars') ||
            document.body.classList.contains('win95') ||
            document.body.classList.contains('retro') ||
            document.body.classList.contains('haxxor');
    }

    function ensureScrollFrame(el) {
        if (!el) return null;
        var parent = el.parentElement;
        if (!parent) return null;
        if (parent.classList.contains('panel-scroll-frame')) {
            return parent;
        }

        var frame = document.createElement('div');
        frame.className = 'panel-scroll-frame';
        if (el.classList.contains('panel-scrollable-list')) {
            frame.classList.add('panel-scroll-frame-list');
        }
        if (el.classList.contains('panel-scrollable-text')) {
            frame.classList.add('panel-scroll-frame-text');
        }
        parent.insertBefore(frame, el);
        frame.appendChild(el);
        return frame;
    }

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
        var thumbMax = parseFloat(computed.getPropertyValue('--panel-scroll-thumb-max-size'));
        var thumbMinRatio = parseFloat(computed.getPropertyValue('--panel-scroll-thumb-min-ratio'));
        var overlayTopOffset = parseFloat(computed.getPropertyValue('--panel-scroll-overlay-top-offset'));
        var overlayHeightScale = parseFloat(computed.getPropertyValue('--panel-scroll-overlay-height-scale'));
        var trackInsetTop = parseFloat(computed.getPropertyValue('--panel-scroll-track-inset-top'));
        var trackInsetBottom = parseFloat(computed.getPropertyValue('--panel-scroll-track-inset-bottom'));
        if (!isFinite(thumbScale) || thumbScale <= 0) thumbScale = 0.5;
        if (!isFinite(thumbMin) || thumbMin <= 0) thumbMin = 12;
        if (!isFinite(thumbMax) || thumbMax <= 0) thumbMax = Infinity;
        if (!isFinite(thumbMinRatio) || thumbMinRatio < 0) thumbMinRatio = 0;
        if (!isFinite(overlayTopOffset)) overlayTopOffset = 0;
        if (!isFinite(overlayHeightScale) || overlayHeightScale <= 0) overlayHeightScale = 1;
        if (!isFinite(trackInsetTop) || trackInsetTop < 0) trackInsetTop = 0;
        if (!isFinite(trackInsetBottom) || trackInsetBottom < 0) trackInsetBottom = 0;
        if (overlayTopOffset === 0 && document.body.classList.contains('lcars')) {
            overlayTopOffset = -3;
        }
        if (document.body.classList.contains('win95')) {
            // Win95: nudge track down 1px and extend overlay height by ~2%.
            if (overlayTopOffset === 0) {
                overlayTopOffset = 1;
            }
            if (overlayHeightScale === 1) {
                overlayHeightScale = 1.02;
            }
        }

        var overlayHeight = Math.round(clientHeight * overlayHeightScale);
        if (overlayTopOffset < 0) {
            overlayHeight = Math.max(0, clientHeight + overlayTopOffset);
        }

        var track = overlay.__trackEl;
        var usableHeight = Math.max(0, overlayHeight - trackInsetTop - trackInsetBottom);
        if (track) {
            track.style.top = trackInsetTop + 'px';
            track.style.bottom = trackInsetBottom + 'px';
            track.style.left = '0px';
            track.style.right = '0px';
        }

        var thumbSize;
        var thumbTop;
        var thumbOpacity;
        var maxTop;

        if (scrollHeight <= clientHeight + 1) {
            thumbSize = Math.max(20, Math.min(usableHeight, Math.round(usableHeight * 0.35)));
            thumbSize = Math.max(thumbMin, Math.round(thumbSize * thumbScale));
            maxTop = Math.max(0, usableHeight - thumbSize);
            thumbTop = Math.round(maxTop / 2);
            thumbOpacity = 0;
        } else {
            var ratio = clientHeight / scrollHeight;
            thumbSize = Math.max(20, Math.round(usableHeight * ratio));
            thumbSize = Math.max(thumbMin, Math.round(thumbSize * thumbScale));
            maxTop = Math.max(0, usableHeight - thumbSize);
            thumbTop = Math.round((el.scrollTop / (scrollHeight - clientHeight)) * maxTop);
            thumbOpacity = 1;
        }

        var cssThumbMin = parseFloat(window.getComputedStyle(thumb).minHeight);
        if (!isFinite(cssThumbMin) || cssThumbMin < 0) cssThumbMin = 0;
        var ratioThumbMin = Math.round(usableHeight * thumbMinRatio);
        var enforcedMin = Math.max(thumbMin, cssThumbMin, ratioThumbMin);
        thumbSize = Math.max(enforcedMin, thumbSize);
        thumbSize = Math.min(thumbSize, thumbMax);
        thumbSize = Math.min(thumbSize, usableHeight);

        maxTop = Math.max(0, usableHeight - thumbSize);
        thumbTop = trackInsetTop + Math.max(0, Math.min(thumbTop, maxTop));

        overlay.style.top = overlayTopOffset + 'px';
        overlay.style.right = '0px';
        overlay.style.height = overlayHeight + 'px';
        thumb.style.height = thumbSize + 'px';
        thumb.style.transform = 'translateY(' + thumbTop + 'px)';
        thumb.style.opacity = String(thumbOpacity);

        el.__customScrollbarMetrics = {
            clientHeight: clientHeight,
            scrollHeight: scrollHeight,
            thumbSize: thumbSize,
            maxTop: maxTop,
            trackInsetTop: trackInsetTop
        };
    }

    function scheduleCustomPanelScrollbarUpdate(el) {
        if (!el) return;
        if (el.__customScrollbarUpdateQueued) {
            return;
        }
        el.__customScrollbarUpdateQueued = true;
        window.requestAnimationFrame(function() {
            window.requestAnimationFrame(function() {
                el.__customScrollbarUpdateQueued = false;
                updateCustomPanelScrollbar(el);
            });
        });
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

        if (window.ResizeObserver && !el.__customScrollbarResizeObserver) {
            var resizeObserver = new ResizeObserver(function() {
                scheduleCustomPanelScrollbarUpdate(el);
            });
            resizeObserver.observe(el);
            resizeObserver.observe(parent);
            el.__customScrollbarResizeObserver = resizeObserver;
        }

        overlay.addEventListener('pointerdown', function(ev) {
            if (ev.target === thumb) return;
            var metrics = el.__customScrollbarMetrics;
            if (!metrics || metrics.scrollHeight <= metrics.clientHeight || metrics.maxTop <= 0) return;
            var rect = overlay.getBoundingClientRect();
            var y = ev.clientY - rect.top - (metrics.trackInsetTop || 0);
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

    function removeCustomScrollbarOverlay(el) {
        if (!el) {
            return;
        }
        if (el.__customScrollbarResizeObserver) {
            el.__customScrollbarResizeObserver.disconnect();
            el.__customScrollbarResizeObserver = null;
        }
        if (el.__customScrollbarOverlay && el.__customScrollbarOverlay.parentNode) {
            el.__customScrollbarOverlay.parentNode.removeChild(el.__customScrollbarOverlay);
        }
        el.__customScrollbarOverlay = null;
        el.__customScrollbarMetrics = null;
    }

    function refreshCustomPanelScrollbars() {
        var scrollEls = document.querySelectorAll('.panel-scrollable-list, .panel-scrollable-text');
        var i;
        if (!useCustomThemeScrollbars()) {
            for (i = 0; i < scrollEls.length; i += 1) {
                removeCustomScrollbarOverlay(scrollEls[i]);
            }
            return;
        }

        for (i = 0; i < scrollEls.length; i += 1) {
            var el = scrollEls[i];
            ensureScrollFrame(el);
            if (!el.__customScrollbarBound) {
                el.__customScrollbarBound = true;
                el.addEventListener('scroll', function(ev) {
                    updateCustomPanelScrollbar(ev.currentTarget);
                });
            }
            ensureCustomScrollbarOverlay(el);
            updateCustomPanelScrollbar(el);
            scheduleCustomPanelScrollbarUpdate(el);
        }
    }

    function updateThemeCarouselScrollbar(el) {
        if (!el) return;
        var overlay = el.__themeCarouselOverlay;
        var clientWidth = el.clientWidth;
        var scrollWidth = el.scrollWidth;
        if (clientWidth <= 0) return;

        var atStart = el.scrollLeft <= 1;
        var atEnd = el.scrollLeft + clientWidth >= scrollWidth - 1;
        if (el.__themeCarouselButtons) {
            if (el.__themeCarouselButtons.prev) {
                el.__themeCarouselButtons.prev.disabled = atStart;
            }
            if (el.__themeCarouselButtons.next) {
                el.__themeCarouselButtons.next.disabled = atEnd;
            }
        }

        if (!overlay) return;
        var thumb = overlay.__thumbEl;
        if (!thumb) return;

        var track = overlay.__trackEl;
        if (track) {
            track.style.left = '0px';
            track.style.right = '0px';
        }

        var thumbWidth;
        var thumbLeft;
        var thumbOpacity;
        var maxLeft;

        if (scrollWidth <= clientWidth + 1) {
            thumbWidth = Math.max(28, Math.min(clientWidth, Math.round(clientWidth * 0.35)));
            maxLeft = Math.max(0, clientWidth - thumbWidth);
            thumbLeft = Math.round(maxLeft / 2);
            thumbOpacity = 0;
        } else {
            var ratio = clientWidth / scrollWidth;
            thumbWidth = Math.max(28, Math.round(clientWidth * ratio));
            maxLeft = Math.max(0, clientWidth - thumbWidth);
            thumbLeft = Math.round((el.scrollLeft / (scrollWidth - clientWidth)) * maxLeft);
            thumbOpacity = 1;
        }

        maxLeft = Math.max(0, clientWidth - thumbWidth);
        thumbLeft = Math.max(0, Math.min(thumbLeft, maxLeft));
        thumb.style.width = thumbWidth + 'px';
        thumb.style.transform = 'translateX(' + thumbLeft + 'px)';
        thumb.style.opacity = String(thumbOpacity);

        el.__themeCarouselMetrics = {
            clientWidth: clientWidth,
            scrollWidth: scrollWidth,
            thumbWidth: thumbWidth,
            maxLeft: maxLeft
        };
    }

    function bindThemeCarouselControls(el) {
        if (!el || el.__themeCarouselControlsBound) {
            return;
        }
        el.__themeCarouselControlsBound = true;

        var frame = el.parentElement;
        if (!frame) return;
        var prevBtn = frame.querySelector('.theme-carousel-button--prev');
        var nextBtn = frame.querySelector('.theme-carousel-button--next');
        el.__themeCarouselButtons = {
            prev: prevBtn,
            next: nextBtn
        };

        function scrollByPage(direction) {
            var amount = Math.max(120, Math.round(el.clientWidth * 0.72)) * direction;
            var target = el.scrollLeft + amount;
            if (typeof el.scrollTo === 'function') {
                el.scrollTo({
                    left: target,
                    behavior: 'smooth'
                });
            } else {
                el.scrollLeft = target;
            }
            updateThemeCarouselScrollbar(el);
        }

        if (prevBtn) {
            prevBtn.addEventListener('click', function(ev) {
                ev.preventDefault();
                scrollByPage(-1);
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', function(ev) {
                ev.preventDefault();
                scrollByPage(1);
            });
        }

        var dragState = null;
        el.addEventListener('pointerdown', function(ev) {
            if (ev.button !== undefined && ev.button !== 0) return;
            if (ev.target.closest && ev.target.closest('.theme-carousel-button')) return;
            ev.preventDefault();
            dragState = {
                pointerId: ev.pointerId,
                startX: ev.clientX,
                startScrollLeft: el.scrollLeft,
                moved: false
            };
            try {
                el.setPointerCapture(ev.pointerId);
            } catch (err) {}
        });

        el.addEventListener('pointermove', function(ev) {
            if (!dragState || dragState.pointerId !== ev.pointerId) return;
            var dx = ev.clientX - dragState.startX;
            if (!dragState.moved && Math.abs(dx) > 4) {
                dragState.moved = true;
                el.classList.add('is-dragging');
                document.body.classList.add('theme-carousel-dragging');
                if (window.getSelection) {
                    var selection = window.getSelection();
                    if (selection && selection.removeAllRanges) {
                        selection.removeAllRanges();
                    }
                }
            }
            if (dragState.moved) {
                ev.preventDefault();
                el.scrollLeft = dragState.startScrollLeft - dx;
                updateThemeCarouselScrollbar(el);
            }
        });

        function endDrag(ev) {
            if (!dragState || dragState.pointerId !== ev.pointerId) return;
            var moved = dragState.moved;
            dragState = null;
            el.classList.remove('is-dragging');
            document.body.classList.remove('theme-carousel-dragging');
            if (moved) {
                el.__suppressThemeCarouselClickUntil = Date.now() + 80;
            }
            try {
                el.releasePointerCapture(ev.pointerId);
            } catch (err) {}
        }

        el.addEventListener('pointerup', endDrag);
        el.addEventListener('pointercancel', endDrag);

        el.addEventListener('click', function(ev) {
            if (el.__suppressThemeCarouselClickUntil &&
                Date.now() < el.__suppressThemeCarouselClickUntil) {
                ev.preventDefault();
                ev.stopPropagation();
            }
        }, true);
    }

    function scrollThemeCarouselToSelection(el) {
        if (!el || el.__themeCarouselInitialScrollDone) {
            return;
        }
        el.__themeCarouselInitialScrollDone = true;

        var selected = el.querySelector('.theme-option.selected');
        if (!selected) {
            var checkedInput = el.querySelector('input[name="theme"]:checked');
            if (checkedInput && checkedInput.closest) {
                selected = checkedInput.closest('.theme-option');
            }
        }
        if (!selected) return;

        var targetLeft = selected.offsetLeft - Math.max(
            0,
            Math.round((el.clientWidth - selected.offsetWidth) / 2)
        );
        targetLeft = Math.max(0, Math.min(
            targetLeft,
            Math.max(0, el.scrollWidth - el.clientWidth)
        ));

        if (typeof el.scrollTo === 'function') {
            el.scrollTo({ left: targetLeft, behavior: 'auto' });
        } else {
            el.scrollLeft = targetLeft;
        }
    }

    function ensureThemeCarouselOverlay(el) {
        if (!el || el.__themeCarouselOverlay) {
            return el ? el.__themeCarouselOverlay : null;
        }
        var frame = el.parentElement;
        if (!frame) return null;
        frame.classList.add('theme-selector-frame--custom');

        var overlay = document.createElement('span');
        overlay.className = 'theme-carousel-scrollbar-overlay';
        var track = document.createElement('span');
        track.className = 'theme-carousel-scrollbar-track';
        var thumb = document.createElement('span');
        thumb.className = 'theme-carousel-scrollbar-thumb';
        overlay.appendChild(track);
        overlay.appendChild(thumb);
        frame.appendChild(overlay);

        el.__themeCarouselOverlay = overlay;
        overlay.__trackEl = track;
        overlay.__thumbEl = thumb;

        overlay.addEventListener('pointerdown', function(ev) {
            if (ev.target === thumb) return;
            var metrics = el.__themeCarouselMetrics;
            if (!metrics || metrics.scrollWidth <= metrics.clientWidth || metrics.maxLeft <= 0) return;
            var rect = overlay.getBoundingClientRect();
            var x = ev.clientX - rect.left;
            var targetLeft = x - (metrics.thumbWidth / 2);
            targetLeft = Math.max(0, Math.min(targetLeft, metrics.maxLeft));
            el.scrollLeft = (targetLeft / metrics.maxLeft) * (metrics.scrollWidth - metrics.clientWidth);
            updateThemeCarouselScrollbar(el);
        });

        thumb.addEventListener('pointerdown', function(ev) {
            ev.preventDefault();
            var startX = ev.clientX;
            var startScrollLeft = el.scrollLeft;
            var metrics = el.__themeCarouselMetrics;
            if (!metrics || metrics.maxLeft <= 0 || metrics.scrollWidth <= metrics.clientWidth) return;
            var pxToScroll = (metrics.scrollWidth - metrics.clientWidth) / metrics.maxLeft;

            try {
                thumb.setPointerCapture(ev.pointerId);
            } catch (err) {}

            function onMove(moveEv) {
                var dx = moveEv.clientX - startX;
                el.scrollLeft = startScrollLeft + (dx * pxToScroll);
                updateThemeCarouselScrollbar(el);
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
            var delta = Math.abs(ev.deltaX) > Math.abs(ev.deltaY) ? ev.deltaX : ev.deltaY;
            el.scrollLeft += delta;
            updateThemeCarouselScrollbar(el);
        }, { passive: false });

        return overlay;
    }

    function refreshThemeCarouselScrollbars() {
        var carousels = document.querySelectorAll('.theme-selector');
        var useCustom = useCustomThemeScrollbars();
        for (var i = 0; i < carousels.length; i += 1) {
            var el = carousels[i];
            if (!el.__themeCarouselBound) {
                el.__themeCarouselBound = true;
                el.addEventListener('scroll', function(ev) {
                    updateThemeCarouselScrollbar(ev.currentTarget);
                });
            }
            bindThemeCarouselControls(el);
            if (useCustom) {
                ensureThemeCarouselOverlay(el);
            }
            scrollThemeCarouselToSelection(el);
            updateThemeCarouselScrollbar(el);
        }
    }

    window.dj4xolRefreshPanelScrollbars = refreshCustomPanelScrollbars;

    document.addEventListener('DOMContentLoaded', function() {
        refreshCustomPanelScrollbars();
        refreshThemeCarouselScrollbars();
        setTimeout(refreshCustomPanelScrollbars, 0);
        setTimeout(refreshThemeCarouselScrollbars, 0);
    });
    document.addEventListener('click', function(ev) {
        var header = ev.target && ev.target.closest ? ev.target.closest('.panel > h2') : null;
        if (!header) return;
        setTimeout(refreshCustomPanelScrollbars, 260);
        setTimeout(refreshThemeCarouselScrollbars, 260);
    });
    window.addEventListener('resize', refreshCustomPanelScrollbars);
    window.addEventListener('resize', refreshThemeCarouselScrollbars);
})();
