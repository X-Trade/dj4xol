(function() {
    function readCookie(name) {
        var cookies = document.cookie ? document.cookie.split(';') : [];
        var prefix = name + '=';
        var idx;
        var cookie;
        for (idx = 0; idx < cookies.length; idx += 1) {
            cookie = cookies[idx].trim();
            if (cookie.indexOf(prefix) === 0) {
                return decodeURIComponent(cookie.substring(prefix.length));
            }
        }
        return '';
    }

    function ensureCsrfToken(form) {
        var token = readCookie('csrftoken');
        var input;
        if (!token) {
            return;
        }
        input = form.querySelector('input[name="csrfmiddlewaretoken"]');
        if (!input) {
            input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'csrfmiddlewaretoken';
            form.appendChild(input);
        }
        input.value = token;
        input.disabled = false;
    }

    function replaceTurnStatus(form) {
        var slot = form.closest('[data-turn-submit-slot]');
        var status;
        if (!slot) {
            return;
        }

        form.style.display = 'none';
        form.setAttribute('aria-hidden', 'true');

        status = slot.querySelector('[data-turn-submit-status="1"]');
        if (!status) {
            status = document.createElement('span');
            status.className = 'status-done';
            status.setAttribute('data-turn-submit-status', '1');
            status.textContent = 'Turned in';
            slot.appendChild(status);
        }
        status.hidden = false;
    }

    function applyTurnSubmissionState(form) {
        if (!form || form.dataset.turnSubmissionUiApplied === '1') {
            return false;
        }

        form.dataset.turnSubmissionUiApplied = '1';
        window.playerTurnedIn = true;
        document.body.classList.add('turned-in');

        // Keep hidden inputs (including csrfmiddlewaretoken) enabled so they are still submitted.
        Array.prototype.forEach.call(form.querySelectorAll('button, input:not([type="hidden"]), select, textarea'), function(control) {
            control.disabled = true;
        });

        replaceTurnStatus(form);

        [
            window.__applyTurnLock,
            window.__applyResearchLock,
            window.__applyDiplomacyLock,
        ].forEach(function(applyLock) {
            if (typeof applyLock === 'function') {
                applyLock();
            }
        });

        if (typeof window.__startTurnPoll === 'function') {
            window.__startTurnPoll();
        }

        return true;
    }

    function initTurnSubmitForms() {
        Array.prototype.forEach.call(document.querySelectorAll('form[data-turn-submit-form="1"]'), function(form) {
            form.addEventListener('submit', function(event) {
                if (form.dataset.turnSubmitting === '1') {
                    event.preventDefault();
                    return;
                }
                form.dataset.turnSubmitting = '1';
                ensureCsrfToken(form);
                window.setTimeout(function() {
                    applyTurnSubmissionState(form);
                }, 0);
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTurnSubmitForms);
    } else {
        initTurnSubmitForms();
    }
})();
