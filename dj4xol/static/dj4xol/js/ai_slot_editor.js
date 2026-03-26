(function() {
    function parseJson(text, fallback) {
        try {
            return JSON.parse(String(text || ""));
        } catch (_err) {
            return fallback;
        }
    }

    function toInt(value, fallback) {
        var parsed = parseInt(value, 10);
        if (!isFinite(parsed)) {
            return fallback;
        }
        return parsed;
    }

    function normalizeCount(value, cap) {
        var count = toInt(value, 0);
        if (count < 0) {
            count = 0;
        }
        if (count > cap) {
            count = cap;
        }
        return count;
    }

    function initAiSlotEditor() {
        var payloadEl = document.getElementById("ai-slot-editor-payload");
        var countInput = document.querySelector('input[name="ai_player_count"]');
        var jsonField = document.querySelector('textarea[name="ai_player_config_json"]');
        var host = document.getElementById("ai-slot-editor-host");
        if (!payloadEl || !countInput || !jsonField || !host) {
            return;
        }

        var payload = parseJson(payloadEl.textContent || "{}", {});
        var modules = Array.isArray(payload.modules) ? payload.modules : [];
        var races = Array.isArray(payload.races) ? payload.races : [];
        var stances = Array.isArray(payload.stances) ? payload.stances : [];
        var capacity = normalizeCount(payload.capacity, 999);
        var maxTech = toInt(payload.max_starting_tech_level, 0);
        if (!modules.length || !races.length || !stances.length || capacity <= 0) {
            return;
        }

        countInput.setAttribute("min", "0");
        countInput.setAttribute("max", String(capacity));

        var selectedRaceId = String(payload.selected_race_id || races[0].id || "");
        var defaultModule = String(modules[0].code || "");
        var defaultStance = String((stances[0] && stances[0].code) || "NEUTRAL");
        var jsonWrap = jsonField.closest(".ai-slot-editor-json-wrap");
        if (jsonWrap) {
            jsonWrap.style.display = "none";
        } else {
            jsonField.style.display = "none";
        }

        function raceById(raceId) {
            for (var i = 0; i < races.length; i++) {
                if (String(races[i].id) === String(raceId)) {
                    return races[i];
                }
            }
            for (var j = 0; j < races.length; j++) {
                if (String(races[j].id) === String(selectedRaceId)) {
                    return races[j];
                }
            }
            return races[0];
        }

        function normalizeSlot(slot, index) {
            var out = {};
            var raw = slot && typeof slot === "object" ? slot : {};

            var moduleCode = String(
                raw.module || raw.ai_module || raw.module_code || defaultModule
            ).toLowerCase();
            var moduleValid = false;
            for (var i = 0; i < modules.length; i++) {
                if (String(modules[i].code) === moduleCode) {
                    moduleValid = true;
                    break;
                }
            }
            if (!moduleValid) {
                moduleCode = defaultModule;
            }
            out.module = moduleCode;

            var raceId = raw.race_id || raw.race || raw.race_short_id || selectedRaceId;
            var race = raceById(raceId);
            out.race_id = String(race.id);

            var fallbackTech = toInt(race.starting_tech_level, 0);
            var tech = toInt(raw.starting_tech_level, fallbackTech);
            if (tech < 0) {
                tech = 0;
            }
            if (tech > maxTech) {
                tech = maxTech;
            }
            out.starting_tech_level = tech;

            var stanceCode = String(
                raw.default_diplomatic_stance || raw.default_stance || defaultStance
            ).toUpperCase();
            var stanceValid = false;
            for (var j = 0; j < stances.length; j++) {
                if (String(stances[j].code) === stanceCode) {
                    stanceValid = true;
                    break;
                }
            }
            if (!stanceValid) {
                stanceCode = defaultStance;
            }
            out.default_diplomatic_stance = stanceCode;
            out.slot = index + 1;
            return out;
        }

        function buildEmptySlot(index) {
            return normalizeSlot({}, index);
        }

        var initialSlots = parseJson(jsonField.value, []);
        if (!Array.isArray(initialSlots)) {
            initialSlots = [];
        }
        var slots = [];

        function resizeSlots() {
            var targetCount = normalizeCount(countInput.value, capacity);
            countInput.value = String(targetCount);
            while (slots.length > targetCount) {
                slots.pop();
            }
            while (slots.length < targetCount) {
                slots.push(buildEmptySlot(slots.length));
            }
            for (var i = 0; i < slots.length; i++) {
                slots[i] = normalizeSlot(slots[i], i);
            }
        }

        function syncJsonField() {
            var serialized = [];
            for (var i = 0; i < slots.length; i++) {
                serialized.push({
                    module: slots[i].module,
                    race_id: slots[i].race_id,
                    starting_tech_level: slots[i].starting_tech_level,
                    default_diplomatic_stance: slots[i].default_diplomatic_stance
                });
            }
            jsonField.value = JSON.stringify(serialized);
        }

        function renderSelect(options, currentValue, onChange) {
            var select = document.createElement("select");
            for (var i = 0; i < options.length; i++) {
                var option = document.createElement("option");
                option.value = String(options[i].value);
                option.textContent = String(options[i].label);
                if (String(options[i].value) === String(currentValue)) {
                    option.selected = true;
                }
                select.appendChild(option);
            }
            select.addEventListener("change", function() {
                onChange(this.value);
                syncJsonField();
            });
            return select;
        }

        function renderEditor() {
            host.innerHTML = "";
            if (!slots.length) {
                host.style.display = "none";
                syncJsonField();
                return;
            }
            host.style.display = "";

            var table = document.createElement("table");
            table.className = "ai-slot-editor-table";
            var header = document.createElement("tr");
            var headers = ["Slot", "AI Type", "Race", "Tech", "Stance"];
            for (var i = 0; i < headers.length; i++) {
                var th = document.createElement("th");
                th.textContent = headers[i];
                header.appendChild(th);
            }
            table.appendChild(header);

            for (var rowIdx = 0; rowIdx < slots.length; rowIdx++) {
                (function(idx) {
                    var slot = slots[idx];
                    var row = document.createElement("tr");

                    var slotCell = document.createElement("td");
                    slotCell.textContent = String(idx + 1);
                    row.appendChild(slotCell);

                    var moduleCell = document.createElement("td");
                    var moduleOptions = [];
                    for (var m = 0; m < modules.length; m++) {
                        moduleOptions.push({
                            value: modules[m].code,
                            label: modules[m].label
                        });
                    }
                    moduleCell.appendChild(renderSelect(moduleOptions, slot.module, function(value) {
                        slots[idx].module = String(value).toLowerCase();
                    }));
                    row.appendChild(moduleCell);

                    var raceCell = document.createElement("td");
                    var raceOptions = [];
                    for (var r = 0; r < races.length; r++) {
                        raceOptions.push({
                            value: races[r].id,
                            label: races[r].label
                        });
                    }
                    raceCell.appendChild(renderSelect(raceOptions, slot.race_id, function(value) {
                        slots[idx].race_id = String(value || races[0].id || "");
                    }));
                    row.appendChild(raceCell);

                    var techCell = document.createElement("td");
                    var techInput = document.createElement("input");
                    techInput.type = "number";
                    techInput.min = "0";
                    techInput.max = String(maxTech);
                    techInput.step = "1";
                    techInput.value = String(slot.starting_tech_level);
                    techInput.className = "number-stepper-input";
                    techInput.addEventListener("change", function() {
                        slots[idx].starting_tech_level = normalizeCount(this.value, maxTech);
                        this.value = String(slots[idx].starting_tech_level);
                        syncJsonField();
                    });
                    techCell.appendChild(techInput);
                    row.appendChild(techCell);

                    var stanceCell = document.createElement("td");
                    var stanceOptions = [];
                    for (var s = 0; s < stances.length; s++) {
                        stanceOptions.push({
                            value: stances[s].code,
                            label: stances[s].label
                        });
                    }
                    stanceCell.appendChild(renderSelect(stanceOptions, slot.default_diplomatic_stance, function(value) {
                        slots[idx].default_diplomatic_stance = String(value).toUpperCase();
                    }));
                    row.appendChild(stanceCell);

                    table.appendChild(row);
                })(rowIdx);
            }

            host.appendChild(table);
            syncJsonField();
        }

        for (var i = 0; i < initialSlots.length; i++) {
            slots.push(normalizeSlot(initialSlots[i], i));
        }
        resizeSlots();
        renderEditor();

        countInput.addEventListener("change", function() {
            resizeSlots();
            renderEditor();
        });
        countInput.addEventListener("input", function() {
            resizeSlots();
            renderEditor();
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAiSlotEditor);
    } else {
        initAiSlotEditor();
    }
})();
