(function() {
    var form = document.querySelector('form.race-form');
    if (!form) {
        return;
    }

    var storage = null;
    try {
        storage = window.sessionStorage || window.localStorage;
    } catch (e) {
        storage = null;
    }
    if (!storage) {
        return;
    }

    var storageKey = 'race-form:' + window.location.pathname;
    var restoreKey = storageKey + ':restore';
    var persistedFieldIds = [
        'id_name',
        'id_plural_name',
        'id_homeworld_name',
        'id_race_type'
    ];

    function readState() {
        var raw = storage.getItem(storageKey);
        if (!raw) {
            return {};
        }
        try {
            var data = JSON.parse(raw);
            return data && typeof data === 'object' ? data : {};
        } catch (e) {
            return {};
        }
    }

    function writeState() {
        var data = {};
        persistedFieldIds.forEach(function(fieldId) {
            var el = document.getElementById(fieldId);
            if (!el) {
                return;
            }
            data[fieldId] = el.value;
        });
        storage.setItem(storageKey, JSON.stringify(data));
    }

    function clearState() {
        storage.removeItem(storageKey);
        storage.removeItem(restoreKey);
    }

    function shouldRestore() {
        var params = new URLSearchParams(window.location.search);
        if (params.get('race_type')) {
            return true;
        }
        return storage.getItem(restoreKey) === '1';
    }

    function restoreState() {
        if (!shouldRestore()) {
            clearState();
            return;
        }
        var data = readState();
        var params = new URLSearchParams(window.location.search);
        persistedFieldIds.forEach(function(fieldId) {
            var el = document.getElementById(fieldId);
            if (!el) {
                return;
            }
            if (fieldId === 'id_race_type') {
                var queryRaceType = params.get('race_type');
                if (queryRaceType) {
                    el.value = queryRaceType;
                    return;
                }
            }
            if (!(fieldId in data)) {
                return;
            }
            el.value = data[fieldId];
            if (fieldId === 'id_plural_name' && data[fieldId]) {
                el.dataset.autofill = 'false';
            }
        });
        storage.removeItem(restoreKey);
    }

    restoreState();

    var browserLink = document.querySelector('[data-race-type-browser-link="1"]');
    if (browserLink) {
        browserLink.addEventListener('click', function() {
            writeState();
            storage.setItem(restoreKey, '1');
        });
    }

    window.addEventListener('pageshow', function(event) {
        if (event.persisted && !shouldRestore()) {
            clearState();
        }
    });

    form.addEventListener('submit', function() {
        clearState();
    });
})();
