(function() {
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
        if (!form || form.dataset.turnSubmitting === '1') {
            return false;
        }

        form.dataset.turnSubmitting = '1';
        window.playerTurnedIn = true;
        document.body.classList.add('turned-in');

        Array.prototype.forEach.call(form.querySelectorAll('button, input, select, textarea'), function(control) {
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
                if (!applyTurnSubmissionState(form)) {
                    event.preventDefault();
                }
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTurnSubmitForms);
    } else {
        initTurnSubmitForms();
    }
})();
