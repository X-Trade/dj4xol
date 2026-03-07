(function() {
    var overlay = document.getElementById('play-terminal-overlay');
    var form = document.getElementById('play-terminal-form');
    var input = document.getElementById('play-terminal-input');
    var output = document.getElementById('play-terminal-output');

    if (!overlay || !form || !input || !output) {
        return;
    }

    var state = {
        isOpen: false,
        bootstrapped: false,
        busy: false,
        dirty: false,
        blocks: [],
        history: [],
        historyIndex: null,
        draftCommand: ''
    };
    var storageKey = 'play-terminal:' + window.location.pathname;

    function getCookie(name) {
        var cookieValue = null;
        if (!document.cookie) {
            return cookieValue;
        }
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i += 1) {
            var cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
        return cookieValue;
    }

    function isEditableTarget(target) {
        if (!target) {
            return false;
        }
        if (target.closest && target.closest('#play-terminal-overlay')) {
            return true;
        }
        if (target.closest && target.closest('#rename-popover')) {
            return true;
        }
        var tagName = (target.tagName || '').toLowerCase();
        if (tagName === 'input' || tagName === 'textarea' || tagName === 'select') {
            return true;
        }
        if (target.isContentEditable) {
            return true;
        }
        if (target.closest && target.closest('[contenteditable="true"]')) {
            return true;
        }
        return false;
    }

    function focusInput() {
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
    }

    function syncOverlayBounds() {
        var titleBar = document.querySelector('.title-bar');
        var top = 0;
        if (titleBar && titleBar.getBoundingClientRect) {
            top = Math.max(0, Math.round(titleBar.getBoundingClientRect().bottom));
        }
        overlay.style.top = top + 'px';
    }

    function scrollOutputToBottom(behavior) {
        var targetTop = output.scrollHeight;
        if (output.scrollTo) {
            try {
                output.scrollTo({
                    top: targetTop,
                    behavior: behavior || 'auto'
                });
                return;
            } catch (e) {}
        }
        output.scrollTop = targetTop;
    }

    function createLineElement(line, isError, isPrompt) {
        var row = document.createElement('div');
        row.className = 'play-terminal-line';
        if (isError) {
            row.classList.add('play-terminal-line-error');
        }
        if (isPrompt) {
            row.classList.add('play-terminal-line-prompt');
        }
        row.textContent = line || '';
        return row;
    }

    function renderBlocks(scrollBehavior) {
        output.innerHTML = '';
        state.blocks.forEach(function(block, idx) {
            var blockEl = document.createElement('div');
            blockEl.className = 'play-terminal-block';
            if (idx !== state.blocks.length - 1) {
                blockEl.classList.add('play-terminal-block-inactive');
            }
            (block.lines || []).forEach(function(line, lineIdx) {
                blockEl.appendChild(
                    createLineElement(line, !!block.isError, !!(block.hasPrompt && lineIdx === 0))
                );
            });
            output.appendChild(blockEl);
        });
        scrollOutputToBottom(scrollBehavior);
    }

    function persistState() {
        try {
            sessionStorage.setItem(storageKey, JSON.stringify({
                isOpen: state.isOpen,
                bootstrapped: state.bootstrapped,
                blocks: state.blocks,
                history: state.history
            }));
        } catch (e) {}
    }

    function clearPersistedState() {
        try {
            sessionStorage.removeItem(storageKey);
        } catch (e) {}
    }

    function restoreState() {
        try {
            var raw = sessionStorage.getItem(storageKey);
            if (!raw) {
                return;
            }
            var saved = JSON.parse(raw);
            if (!saved || !Array.isArray(saved.blocks)) {
                return;
            }
            state.blocks = saved.blocks;
            state.bootstrapped = !!saved.bootstrapped;
            state.history = Array.isArray(saved.history) ? saved.history : [];
            renderBlocks();
            if (saved.isOpen) {
                state.isOpen = true;
                syncOverlayBounds();
                overlay.hidden = false;
                document.body.classList.add('play-terminal-open');
                setPromptValue('');
                requestAnimationFrame(function() {
                    scrollOutputToBottom('auto');
                });
            }
        } catch (e) {}
    }

    function appendBlock(lines, isError, hasPrompt) {
        state.blocks.push({
            lines: (lines || []).slice(),
            isError: !!isError,
            hasPrompt: !!hasPrompt
        });
        renderBlocks(hasPrompt ? 'smooth' : 'auto');
        persistState();
    }

    function rememberCommand(command) {
        if (!command) {
            return;
        }
        if (!state.history.length || state.history[state.history.length - 1] !== command) {
            state.history.push(command);
        }
        state.historyIndex = null;
        state.draftCommand = '';
        persistState();
    }

    function moveHistory(direction) {
        if (!state.history.length) {
            return;
        }
        if (state.historyIndex === null) {
            if (direction > 0) {
                return;
            }
            state.draftCommand = input.value || '';
            state.historyIndex = state.history.length - 1;
        } else {
            state.historyIndex += direction;
            if (state.historyIndex < 0) {
                state.historyIndex = 0;
            }
            if (state.historyIndex >= state.history.length) {
                state.historyIndex = null;
                setPromptValue(state.draftCommand || '');
                return;
            }
        }
        setPromptValue(state.history[state.historyIndex] || '');
    }

    function appendCommandBlock(command, lines, isError) {
        var blockLines = ['play> ' + command];
        Array.prototype.push.apply(blockLines, lines || []);
        appendBlock(blockLines, isError, true);
    }

    function setPromptValue(value) {
        input.value = value;
        focusInput();
    }

    function openOverlay() {
        if (state.isOpen) {
            setPromptValue(input.value || '/');
            return;
        }
        state.isOpen = true;
        syncOverlayBounds();
        overlay.hidden = false;
        document.body.classList.add('play-terminal-open');
        setPromptValue('/');
        persistState();
        if (!state.bootstrapped) {
            bootstrap();
        }
    }

    function closeOverlay() {
        state.isOpen = false;
        overlay.hidden = true;
        document.body.classList.remove('play-terminal-open');
        input.blur();
        clearPersistedState();
        if (state.dirty) {
            state.dirty = false;
            window.location.reload();
        }
    }

    function bootstrap() {
        if (!window.playCliBootstrapUrl) {
            return;
        }
        fetch(window.playCliBootstrapUrl, {
            credentials: 'same-origin',
            cache: 'no-store'
        })
            .then(function(resp) { return resp.json(); })
            .then(function(data) {
                state.bootstrapped = true;
                appendBlock(data && data.lines ? data.lines : [], false, false);
            })
            .catch(function() {
                appendBlock(['Unable to start Play CLI overlay.'], true, false);
            });
    }

    function navigateToSelection(target) {
        if (!target || !target.sel) {
            return;
        }
        if (typeof window.persistStarmapScrollPosition === 'function') {
            window.persistStarmapScrollPosition();
        }
        persistState();
        var params = new URLSearchParams(window.location.search);
        params.set('sel', target.sel);
        if (target.x !== undefined && target.x !== null) {
            params.set('x', target.x);
        } else {
            params.delete('x');
        }
        if (target.y !== undefined && target.y !== null) {
            params.set('y', target.y);
        } else {
            params.delete('y');
        }
        if (target.locate) {
            params.set('locate', '1');
        } else {
            params.delete('locate');
        }
        window.location.search = params.toString();
    }

    function submitCommand(command) {
        if (!window.playCliCommandUrl || state.busy) {
            return;
        }
        var lowered = (command || '').toLowerCase();
        if (lowered === '/exit' || lowered === '/quit') {
            closeOverlay();
            return;
        }
        state.busy = true;
        rememberCommand(command);

        fetch(window.playCliCommandUrl, {
            method: 'POST',
            credentials: 'same-origin',
            cache: 'no-store',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ command: command })
        })
            .then(function(resp) {
                return resp.json().then(function(data) {
                    return { status: resp.status, data: data };
                });
            })
            .then(function(result) {
                var payload = result.data || {};
                appendCommandBlock(command, payload.lines || [], !payload.ok);
                if (payload.ok && payload.mutated) {
                    state.dirty = true;
                }
                if (payload.close_overlay) {
                    closeOverlay();
                } else if (payload.navigate_to) {
                    navigateToSelection(payload.navigate_to);
                } else if (state.isOpen) {
                    setPromptValue('');
                }
            })
            .catch(function() {
                appendCommandBlock(command, ['Play CLI request failed.'], true);
                if (state.isOpen) {
                    setPromptValue('');
                }
            })
            .finally(function() {
                state.busy = false;
            });
    }

    document.addEventListener('keydown', function(ev) {
        if (state.isOpen && ev.key === 'Escape') {
            ev.preventDefault();
            ev.stopPropagation();
            closeOverlay();
            return;
        }
        if (ev.key !== '/') {
            return;
        }
        if (ev.ctrlKey || ev.metaKey || ev.altKey) {
            return;
        }
        if (state.isOpen) {
            return;
        }
        if (isEditableTarget(ev.target)) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        openOverlay();
    }, true);

    overlay.addEventListener('click', function(ev) {
        if (ev.target === overlay || ev.target.classList.contains('play-terminal-backdrop')) {
            focusInput();
        }
    });

    output.addEventListener('click', function() {
        var selection = window.getSelection ? window.getSelection() : null;
        if (selection && String(selection).length > 0) {
            return;
        }
        focusInput();
    });

    window.addEventListener('resize', function() {
        if (state.isOpen) {
            syncOverlayBounds();
        }
    });

    form.addEventListener('submit', function(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var command = (input.value || '').trim();
        if (!command) {
            setPromptValue('');
            return;
        }
        submitCommand(command);
    });

    input.addEventListener('keydown', function(ev) {
        ev.stopPropagation();
        if (ev.key === 'Escape') {
            ev.preventDefault();
            closeOverlay();
            return;
        }
        if (ev.key === 'ArrowUp') {
            ev.preventDefault();
            moveHistory(-1);
            return;
        }
        if (ev.key === 'ArrowDown') {
            ev.preventDefault();
            moveHistory(1);
        }
    });

    document.addEventListener('keydown', function(ev) {
        if (ev.defaultPrevented) {
            return;
        }
        if (!state.isOpen || state.busy) {
            return;
        }
        if (ev.target === input || isEditableTarget(ev.target)) {
            return;
        }
        if (ev.ctrlKey || ev.metaKey || ev.altKey) {
            return;
        }
        if (ev.key === 'Tab') {
            return;
        }
        if (ev.key === 'ArrowUp') {
            ev.preventDefault();
            focusInput();
            moveHistory(-1);
            return;
        }
        if (ev.key === 'ArrowDown') {
            ev.preventDefault();
            focusInput();
            moveHistory(1);
            return;
        }
        if (ev.key === 'Backspace') {
            ev.preventDefault();
            focusInput();
            input.value = (input.value || '').slice(0, -1);
            return;
        }
        if (ev.key === 'Enter') {
            ev.preventDefault();
            focusInput();
            form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event('submit', { cancelable: true }));
            return;
        }
        if (ev.key.length === 1) {
            ev.preventDefault();
            focusInput();
            input.value = (input.value || '') + ev.key;
        }
    }, true);

    restoreState();
})();
