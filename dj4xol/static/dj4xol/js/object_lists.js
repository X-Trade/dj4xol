(function() {
    function numericValue(value) {
        var cleaned = String(value || '').replace(/[^0-9.\-]/g, '');
        if (!cleaned) return null;
        var parsed = Number(cleaned);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function rowSortValue(row, key) {
        var cell = row.querySelector('[data-sort-cell="' + key + '"]');
        if (!cell) return '';
        return cell.getAttribute('data-sort-value') || cell.textContent || '';
    }

    function storageKey(table) {
        return 'dj4xol:object-list-order:' + window.location.pathname + ':' + (table.dataset.tableId || 'default');
    }

    function dataRows(tbody) {
        return Array.prototype.slice.call(tbody.querySelectorAll('tr[data-object-id]'));
    }

    function saveOrder(table, tbody) {
        var order = dataRows(tbody).map(function(row) {
            return row.getAttribute('data-object-id');
        }).filter(Boolean);
        try {
            window.localStorage.setItem(storageKey(table), JSON.stringify(order));
        } catch (err) {
            return;
        }
    }

    function applySavedOrder(table, tbody) {
        var raw = null;
        try {
            raw = window.localStorage.getItem(storageKey(table));
        } catch (err) {
            raw = null;
        }
        if (!raw) return;
        var order;
        try {
            order = JSON.parse(raw);
        } catch (err) {
            return;
        }
        if (!Array.isArray(order) || !order.length) return;
        var rows = dataRows(tbody);
        var byId = {};
        rows.forEach(function(row) {
            byId[row.getAttribute('data-object-id')] = row;
        });
        order.forEach(function(id) {
            if (byId[id]) {
                tbody.appendChild(byId[id]);
                delete byId[id];
            }
        });
        rows.forEach(function(row) {
            if (byId[row.getAttribute('data-object-id')]) {
                tbody.appendChild(row);
            }
        });
    }

    function selectedIds(table, scope) {
        if (scope === 'all') {
            return dataRows(table.tBodies[0]).map(function(row) {
                return row.getAttribute('data-object-id');
            }).filter(Boolean);
        }
        return Array.prototype.slice.call(
            table.querySelectorAll('input[data-object-select]:checked')
        ).map(function(input) {
            return input.value;
        }).filter(Boolean);
    }

    function initBulkForms(table) {
        var forms = document.querySelectorAll('form[data-object-list-bulk-form="' + table.dataset.tableId + '"]');
        var updateButtons = function() {
            var hasRows = dataRows(table.tBodies[0]).length > 0;
            var selectedCount = selectedIds(table, 'selected').length;
            Array.prototype.forEach.call(forms, function(form) {
                var button = form.querySelector('[data-object-list-bulk-button]');
                if (!button) return;
                var scope = form.getAttribute('data-bulk-scope');
                if (scope === 'all') {
                    button.disabled = !hasRows;
                } else {
                    button.disabled = selectedCount === 0;
                }
            });
        };
        Array.prototype.forEach.call(forms, function(form) {
            form.addEventListener('submit', function(ev) {
                var ids = selectedIds(table, form.getAttribute('data-bulk-scope'));
                var input = form.querySelector('input[name="object_ids"]');
                if (input) input.value = ids.join(',');
                if (!ids.length) {
                    ev.preventDefault();
                }
            });
        });
        Array.prototype.forEach.call(
            table.querySelectorAll('input[data-object-select]'),
            function(input) {
                input.addEventListener('change', updateButtons);
            }
        );
        var toggle = table.querySelector('[data-object-select-all]');
        if (toggle) {
            toggle.addEventListener('change', updateButtons);
        }
        updateButtons();
    }

    function initSelectAll(table) {
        var toggle = table.querySelector('[data-object-select-all]');
        if (!toggle) return;
        toggle.addEventListener('change', function() {
            Array.prototype.forEach.call(
                table.querySelectorAll('input[data-object-select]'),
                function(input) {
                    input.checked = toggle.checked;
                }
            );
        });
    }

    function initSorting(table, tbody) {
        var current = { key: null, direction: 'asc' };
        Array.prototype.forEach.call(table.querySelectorAll('th[data-sort-key]'), function(header) {
            header.addEventListener('click', function() {
                var key = header.getAttribute('data-sort-key');
                var direction = current.key === key && current.direction === 'asc' ? 'desc' : 'asc';
                current = { key: key, direction: direction };
                Array.prototype.forEach.call(table.querySelectorAll('th[data-sort-key]'), function(other) {
                    other.classList.remove('sort-asc', 'sort-desc');
                });
                header.classList.add(direction === 'asc' ? 'sort-asc' : 'sort-desc');
                var rows = dataRows(tbody);
                rows.sort(function(a, b) {
                    var av = rowSortValue(a, key);
                    var bv = rowSortValue(b, key);
                    var an = numericValue(av);
                    var bn = numericValue(bv);
                    var result;
                    if (an !== null && bn !== null) {
                        result = an - bn;
                    } else {
                        result = String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: 'base' });
                    }
                    return direction === 'asc' ? result : -result;
                });
                rows.forEach(function(row) {
                    tbody.appendChild(row);
                });
            });
        });
    }

    function initDrag(table, tbody) {
        var dragging = null;
        dataRows(tbody).forEach(function(row) {
            var handle = row.querySelector('[data-object-drag-handle]');
            if (!handle) return;
            row.setAttribute('draggable', 'true');
            handle.setAttribute('aria-label', 'Reorder row');
            row.addEventListener('dragstart', function(ev) {
                dragging = row;
                row.classList.add('is-dragging');
                ev.dataTransfer.effectAllowed = 'move';
                ev.dataTransfer.setData('text/plain', row.getAttribute('data-object-id') || '');
            });
            row.addEventListener('dragend', function() {
                row.classList.remove('is-dragging');
                dragging = null;
                saveOrder(table, tbody);
            });
            row.addEventListener('dragover', function(ev) {
                if (!dragging || dragging === row) return;
                ev.preventDefault();
                var rect = row.getBoundingClientRect();
                var after = ev.clientY > rect.top + rect.height / 2;
                tbody.insertBefore(dragging, after ? row.nextSibling : row);
            });
        });
    }

    function initTable(table) {
        var tbody = table.querySelector('[data-object-table-body]');
        if (!tbody) return;
        applySavedOrder(table, tbody);
        initSelectAll(table);
        initBulkForms(table);
        initSorting(table, tbody);
        initDrag(table, tbody);
    }

    function initNavigationMenu() {
        var hamburger = document.getElementById('hamburger-btn');
        var dropdown = document.getElementById('nav-dropdown');
        if (!hamburger || !dropdown) return;
        hamburger.addEventListener('click', function(ev) {
            ev.stopPropagation();
            dropdown.classList.toggle('open');
            hamburger.classList.toggle('open');
        });
        document.addEventListener('click', function(ev) {
            if (!dropdown.contains(ev.target) && !hamburger.contains(ev.target)) {
                dropdown.classList.remove('open');
                hamburger.classList.remove('open');
            }
        });
    }

    function initPanelToggles() {
        Array.prototype.forEach.call(document.querySelectorAll('.panel'), function(panel) {
            var header = panel.querySelector('h2');
            if (!header) return;
            header.addEventListener('click', function() {
                panel.classList.remove('no-transition');
                panel.classList.toggle('open');
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        initNavigationMenu();
        initPanelToggles();
        Array.prototype.forEach.call(document.querySelectorAll('[data-object-table]'), initTable);
    });
})();
