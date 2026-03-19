(function() {
    function getStorage() {
        try {
            return window.sessionStorage;
        } catch (err) {
            return null;
        }
    }

    function parseJson(raw) {
        if (!raw) {
            return null;
        }
        try {
            return JSON.parse(raw);
        } catch (err) {
            return null;
        }
    }

    function isFreshPending(pending) {
        if (!pending || !pending.ts) {
            return false;
        }
        return Math.abs(Date.now() - pending.ts) <= 60000;
    }

    function shouldPersistLink(anchor) {
        if (!anchor || !anchor.getAttribute) {
            return false;
        }
        var rawHref = anchor.getAttribute('href') || '';
        if (!rawHref || rawHref.charAt(0) === '#') {
            return false;
        }
        if (rawHref.indexOf('?') === 0) {
            return true;
        }
        try {
            var url = new URL(anchor.href, window.location.href);
            return url.origin === window.location.origin && url.pathname === window.location.pathname;
        } catch (err) {
            return false;
        }
    }

    function eventAllowsNavigation(ev) {
        if (!ev || ev.defaultPrevented) {
            return false;
        }
        if (ev.button !== undefined && ev.button !== 0) {
            return false;
        }
        if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) {
            return false;
        }
        return true;
    }

    window.initScopedUiStatePersistence = function(options) {
        var opts = options || {};
        var root = document.querySelector(opts.rootSelector || 'body');
        var storage = getStorage();
        if (!root || !storage) {
            return {
                saveAndMark: function() {},
                clearPending: function() {},
            };
        }

        var baseKey = 'page-ui:' + (opts.namespace || 'default') + ':' + window.location.pathname;
        var stateKey = baseKey + ':state';
        var pendingKey = baseKey + ':pending';

        function panelKey(panel, index) {
            return panel.getAttribute('data-panel') || panel.id || ('panel-' + index);
        }

        function scrollKey(el, index) {
            var panel = el.closest('.panel[data-panel]');
            var panelPart = panel ? panel.getAttribute('data-panel') : 'page';
            var kind = el.id || (el.classList.contains('panel-scrollable-list') ? 'list' : 'text');
            return panelPart + ':' + kind + ':' + index;
        }

        function collectState(includeScrolls) {
            var shouldIncludeScrolls = includeScrolls !== false;
            var state = {
                panels: {},
                scrolls: {},
            };

            var panels = root.querySelectorAll(opts.panelSelector || '.panel[data-panel]');
            Array.prototype.forEach.call(panels, function(panel, index) {
                state.panels[panelKey(panel, index)] = panel.classList.contains('open');
            });

            if (shouldIncludeScrolls) {
                var scrollEls = root.querySelectorAll(opts.scrollSelector || '.panel-scrollable-list, .panel-scrollable-text');
                Array.prototype.forEach.call(scrollEls, function(el, index) {
                    state.scrolls[scrollKey(el, index)] = {
                        top: el.scrollTop || 0,
                        left: el.scrollLeft || 0,
                    };
                });
            }

            return state;
        }

        function applyState(state) {
            if (!state) {
                return;
            }

            var panels = root.querySelectorAll(opts.panelSelector || '.panel[data-panel]');
            Array.prototype.forEach.call(panels, function(panel, index) {
                var key = panelKey(panel, index);
                if (Object.prototype.hasOwnProperty.call(state.panels, key)) {
                    panel.classList.toggle('open', !!state.panels[key]);
                }
            });

            function applyScrolls() {
                var scrollEls = root.querySelectorAll(opts.scrollSelector || '.panel-scrollable-list, .panel-scrollable-text');
                Array.prototype.forEach.call(scrollEls, function(el, index) {
                    var saved = state.scrolls[scrollKey(el, index)];
                    if (!saved) {
                        return;
                    }
                    el.scrollTop = saved.top || 0;
                    el.scrollLeft = saved.left || 0;
                });
                if (typeof window.dj4xolRefreshPanelScrollbars === 'function') {
                    window.dj4xolRefreshPanelScrollbars();
                } else {
                    setTimeout(function() {
                        if (typeof window.dj4xolRefreshPanelScrollbars === 'function') {
                            window.dj4xolRefreshPanelScrollbars();
                        }
                    }, 0);
                }
            }

            window.requestAnimationFrame(function() {
                window.requestAnimationFrame(applyScrolls);
            });
        }

        function saveAndMark(config) {
            var cfg = config || {};
            storage.setItem(stateKey, JSON.stringify(collectState(cfg.includeScrolls)));
            storage.setItem(pendingKey, JSON.stringify({ ts: Date.now() }));
        }

        function clearPending() {
            storage.removeItem(pendingKey);
        }

        var pending = parseJson(storage.getItem(pendingKey));
        if (isFreshPending(pending)) {
            clearPending();
            applyState(parseJson(storage.getItem(stateKey)));
        } else {
            clearPending();
        }

        Array.prototype.forEach.call(root.querySelectorAll(opts.persistFormSelector || 'form'), function(form) {
            form.addEventListener('submit', function() {
                var includeScrolls = true;
                if (opts.noScrollFormSelector && form.matches && form.matches(opts.noScrollFormSelector)) {
                    includeScrolls = false;
                }
                saveAndMark({ includeScrolls: includeScrolls });
            });
        });

        root.addEventListener('click', function(ev) {
            var anchor = ev.target && ev.target.closest ? ev.target.closest(opts.persistLinkSelector || 'a[href]') : null;
            if (!anchor || !shouldPersistLink(anchor) || !eventAllowsNavigation(ev)) {
                return;
            }
            var includeScrolls = true;
            if (opts.noScrollLinkSelector && anchor.matches && anchor.matches(opts.noScrollLinkSelector)) {
                includeScrolls = false;
            }
            saveAndMark({ includeScrolls: includeScrolls });
        });

        return {
            saveAndMark: saveAndMark,
            clearPending: clearPending,
        };
    };
})();
