(function() {
    function parseBoundary(raw) {
        if (raw === null || raw === undefined || raw === '') {
            return null;
        }
        var value = parseFloat(raw);
        return isNaN(value) ? null : value;
    }

    function clampToBounds(input, value) {
        var min = parseBoundary(input.getAttribute('min'));
        var max = parseBoundary(input.getAttribute('max'));
        if (min !== null && value < min) {
            value = min;
        }
        if (max !== null && value > max) {
            value = max;
        }
        return value;
    }

    function normalizeNumericString(value, step) {
        if (!isFinite(value)) {
            return '';
        }
        var stepString = String(step || '1');
        var decimals = stepString.indexOf('.') === -1 ? 0 : stepString.split('.')[1].length;
        if (!decimals) {
            return String(Math.round(value));
        }
        return value.toFixed(decimals).replace(/\.?0+$/, '');
    }

    function parseStepThresholds(input) {
        var raw = (input.getAttribute('data-step-thresholds') || '').trim();
        if (!raw) {
            return [];
        }
        return raw.split(',').map(function(part) {
            var pieces = part.split(':');
            if (pieces.length !== 2) {
                return null;
            }
            var threshold = parseFloat(pieces[0]);
            var step = parseFloat(pieces[1]);
            if (!isFinite(threshold) || !isFinite(step) || step <= 0) {
                return null;
            }
            return {
                threshold: threshold,
                step: step,
            };
        }).filter(Boolean).sort(function(a, b) {
            return a.threshold - b.threshold;
        });
    }

    function resolveStepAmount(input, direction) {
        var stepAttr = input.getAttribute('step');
        var defaultStep = stepAttr && stepAttr !== 'any' ? parseFloat(stepAttr) : 1;
        if (!isFinite(defaultStep) || defaultStep <= 0) {
            defaultStep = 1;
        }

        var thresholds = parseStepThresholds(input);
        if (!thresholds.length) {
            return defaultStep;
        }

        var current = parseFloat(input.value);
        if (!isFinite(current)) {
            var min = parseBoundary(input.getAttribute('min'));
            current = min !== null ? min : 0;
        }

        if (direction < 0) {
            current -= 1e-9;
        }

        var resolvedStep = defaultStep;
        thresholds.forEach(function(rule) {
            if (current >= rule.threshold) {
                resolvedStep = rule.step;
            }
        });
        return resolvedStep;
    }

    function dispatchNumberInputEvents(input) {
        ['input', 'change'].forEach(function(type) {
            input.dispatchEvent(new Event(type, { bubbles: true }));
        });
    }

    function syncStepperButtons(input, minusButton, plusButton) {
        var disabled = !!input.disabled;
        var min = parseBoundary(input.getAttribute('min'));
        var max = parseBoundary(input.getAttribute('max'));
        var current = parseBoundary(input.value);

        minusButton.disabled = disabled || (current !== null && min !== null && current <= min);
        plusButton.disabled = disabled || (current !== null && max !== null && current >= max);
    }

    function applyStep(input, direction) {
        if (!input || input.disabled) {
            return;
        }

        if (input.readOnly) {
            input.removeAttribute('readonly');
        }

        if (document.activeElement !== input && typeof input.focus === 'function') {
            try {
                input.focus({ preventScroll: true });
            } catch (err) {
                input.focus();
            }
        }

        var step = resolveStepAmount(input, direction);
        var current = parseFloat(input.value);
        if (!isFinite(current)) {
            var min = parseBoundary(input.getAttribute('min'));
            current = min !== null ? min : 0;
        } else {
            current += step * direction;
        }
        current = clampToBounds(input, current);
        input.value = normalizeNumericString(current, step);

        dispatchNumberInputEvents(input);
    }

    function enhanceNumberInput(input) {
        if (!input || input.dataset.stepperEnhanced === '1' || input.closest('.number-stepper')) {
            return;
        }

        input.dataset.stepperEnhanced = '1';

        var wrapper = document.createElement('span');
        wrapper.className = 'number-stepper';
        if (input.classList.contains('quantity-input')) {
            wrapper.classList.add('number-stepper--compact');
        }

        var minusButton = document.createElement('button');
        minusButton.type = 'button';
        minusButton.className = 'number-stepper-btn number-stepper-btn--minus';
        minusButton.setAttribute('aria-label', 'Decrease value');
        minusButton.textContent = '-';

        var plusButton = document.createElement('button');
        plusButton.type = 'button';
        plusButton.className = 'number-stepper-btn number-stepper-btn--plus';
        plusButton.setAttribute('aria-label', 'Increase value');
        plusButton.textContent = '+';

        var parent = input.parentNode;
        if (!parent) {
            return;
        }

        parent.insertBefore(wrapper, input);
        wrapper.appendChild(minusButton);
        wrapper.appendChild(input);
        wrapper.appendChild(plusButton);
        input.classList.add('number-stepper-input');

        minusButton.addEventListener('click', function() {
            applyStep(input, -1);
            syncStepperButtons(input, minusButton, plusButton);
        });
        plusButton.addEventListener('click', function() {
            applyStep(input, 1);
            syncStepperButtons(input, minusButton, plusButton);
        });

        input.addEventListener('input', function() {
            syncStepperButtons(input, minusButton, plusButton);
        });
        input.addEventListener('change', function() {
            syncStepperButtons(input, minusButton, plusButton);
        });

        if (window.MutationObserver) {
            var observer = new MutationObserver(function() {
                syncStepperButtons(input, minusButton, plusButton);
            });
            observer.observe(input, {
                attributes: true,
                attributeFilter: ['disabled', 'min', 'max', 'value'],
            });
        }

        syncStepperButtons(input, minusButton, plusButton);
    }

    function initNumberSteppers(root) {
        var scope = root && root.querySelectorAll ? root : document;
        var inputs = scope.querySelectorAll('input[type="number"]:not([data-stepper-ignore="1"])');
        Array.prototype.forEach.call(inputs, function(input) {
            enhanceNumberInput(input);
        });
    }

    window.initNumberSteppers = initNumberSteppers;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            initNumberSteppers(document);
        });
    } else {
        initNumberSteppers(document);
    }
})();
