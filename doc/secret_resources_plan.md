# Secret Resources Plan

**Summary**
Add three hidden resources (`resource_x`, `resource_y`, `resource_z`) that are globally nameable via server settings, only visible to a player/account once discovered, and usable in research requirements and production costs. Each resource spawns on exactly one star per game, never on a homeworld, and not co-located. Discovery is account-level and unlocks naming in research/help screens and inventory displays.

**Terminology**
- Internal keys: `resource_x`, `resource_y`, `resource_z`
- Default display names (server settings): Uniquium, Rarium, Mysterium
- “Discovered” means the account has encountered the resource in any game

**Player-Facing Rules**
- Secret resources are hidden unless present in the viewed inventory/report.
- If present but not discovered, display label as `???`.
- Transfer dialogs show secret resources only if source or target has them.
- Research/help screens show `???` for requirements tied to undiscovered secret resources.
- Once discovered (account-level), names are shown everywhere in non-game UI and remain known in all games.
- Within a game, per-player discovery controls in-game visibility.

**Discovery Rules**
- Discovery is recorded on both `Account` (global) and per-game player state (race context), and is permanent.
- Discovery occurs when:
  - A player receives an advanced or encounter report that includes a star with the resource present.
  - A player’s fleet acquires the resource into cargo.
  - A player’s star has the resource in surface inventory (ownership report or direct visit).
- Discovery does not occur from research screens alone; only world/fleet exposure counts.

**Data Model Changes**
- `Account`
  - Add `discovered_resource_x`, `discovered_resource_y`, `discovered_resource_z` (BooleanFields, default False).
- `Player` (per-game race context used for in-game display)
  - Add `discovered_resource_x`, `discovered_resource_y`, `discovered_resource_z` (BooleanFields, default False).
- `Star`
  - Add `resource_x_inventory`, `resource_y_inventory`, `resource_z_inventory` (IntegerFields, default 0).
  - Optional: add `resource_x_yield`, `resource_y_yield`, `resource_z_yield` if we want mining-based generation.
- `Fleet`
  - Add `resource_x_inventory`, `resource_y_inventory`, `resource_z_inventory` (IntegerFields, default 0).
- `Salvage`
  - Add `resource_x_inventory`, `resource_y_inventory`, `resource_z_inventory` (IntegerFields, default 0).
- `FleetOrders` (transfer)
  - Add `transfer_resource_x`, `transfer_resource_y`, `transfer_resource_z` (IntegerFields, default 0).
- `PlayerResearch`
  - Add `resource_x_paid`, `resource_y_paid`, `resource_z_paid` (IntegerFields, default 0).
- `DefaultResearchLevelRequirement` and `ResearchLevelRequirement`
  - Add `resource_x_cost`, `resource_y_cost`, `resource_z_cost` (IntegerFields, default 0).
- Production cost models (where `ironium_cost` exists)
  - Add `resource_x_cost`, `resource_y_cost`, `resource_z_cost` to `HullDesign`, `ProductionOrder`, and any other production-related model using mineral cost fields.

**Server Settings**
- Add new `ServerSettings` keys in `dj4xol/fixtures/defaults.yaml`:
  - `secret_resource_x_name` = `Uniquium`
  - `secret_resource_y_name` = `Rarium`
  - `secret_resource_z_name` = `Mysterium`
- Add helper accessors to map internal keys to display names, falling back to defaults.

**Game Generation (Factory)**
- Add a placement step after homeworlds are assigned so we can avoid them.
- For each secret resource:
  - Choose exactly one star that is not a homeworld and does not already have another secret resource.
  - On very large maps (both dimensions > 200px and > 150 stars), allow *rarely* placing a second star for that resource.
  - Enforce a minimum distance from all homeworlds (use `_min_homeworld_distance()` or a new constant like `SECRET_RESOURCE_MIN_HOMEWORLD_DISTANCE = 1.25 * _min_homeworld_distance()`).
  - If no star satisfies the distance constraint, fall back to the farthest non-homeworld star.
  - Ensure placement is not co-located with another secret resource even if stars share coordinates (systems).
- Deposit rules:
  - Place a surface inventory amount comparable to Germanium defaults.
  - Set yield to at least 50% for each secret resource (yield is the main signal for players).

**Rules/Logic Changes**
- Extend mineral handling utilities to include secret resources:
  - Inventory totals, capacity usage, transfers, and salvage calculations.
  - Remote mining and standard mining should extract secret resources when yields exist.
  - Research mineral consumption logic (`research.py`) to include the new cost/paid/inventory fields.
- Update report building (`turn.py` + `objectdetails.py`) to conditionally include secret resource inventories:
  - Include only if amount > 0.
  - Use `???` as the label when the *player* has not discovered the resource (in-game UI).
  - When scanning enemy fleets carrying secret resources, show numeric amounts but label as `???` until discovered.
- Update discovery tracking where reports are created or where inventory changes:
  - On report generation, inspect star/fleet data and mark discovery on both `Player` and `Account` if resource present.
  - On transfers and mining/production, if a player’s inventory gains a secret resource, mark discovery on both `Player` and `Account`.

**UI/UX Changes**
- Detail panel (`dj4xol/objectdetails.py`, `dj4xol/templates/dj4xol/_detail_panel.html`)
  - Render secret resources only when present.
  - Display names or `???` based on player discovery.
- Orders panel (`dj4xol/templates/dj4xol/_orders_panel.html` + Brython if needed)
  - Show transfer sliders/inputs only if source or target has secret resources.
  - Use `???` when undiscovered.
- Production panel (`dj4xol/templates/dj4xol/_production_panel.html`)
  - Display secret resource costs only if they exist on the item.
  - Mask names with `???` if undiscovered.
- Research UI (`dj4xol/templates/dj4xol/research.html`, `dj4xol/templates/dj4xol/help_technology.html`)
  - Show `???` labels for secret resource requirements until discovery.
  - Use account discovery for help/technology directory views outside a specific game context.

**Messaging**
- Add a message factory for discovery events with variants:
  - Example template: "{fleet_phrase} discovered a {adjective} new element on {star}. {naming_phrase} '{secret_name}'. {impact_phrase}"
  - Generate a priority message on first discovery per account.
- Avoid duplicate messages if a resource is already discovered.

**Research Integration**
- Extend research requirement resolution to include secret resource costs.
- Ensure mineral payment allocation and progress tracking include secret resources.
- Research gating should respect unknown resources while masking the name in UI.

**Production Integration**
- Extend production cost calculations to include secret resources.
- Allow items to specify secret resource costs in admin/UI.
- Ensure production failures communicate missing resources, masking names if undiscovered.

**Admin/Tools**
- Add admin field display for new costs and inventories.
- Add management command or admin tools to reveal/clear discovery per account if needed.

**Tests**
- Add coverage for:
  - Discovery on advanced scan and on transfer.
  - Hidden vs. revealed display in reports and panels.
  - Research requirements with `???` labels before discovery.
  - Production costs with secret resources.
  - Game creation ensures exactly one deposit per resource, not on homeworld, not co-located.

**Migration/Backfill**
- Add migrations for new fields in models.
- Defaults should leave all secret resources undiscovered and inventories at 0.
- No data backfill required beyond defaults unless we want to seed a live game.

**Open Questions / Assumptions**
- Resource amounts: default deposit size per resource should be comparable to Germanium.
- Mining behavior: secret resources are mineable over time using standard depletion rules.
- Visibility of amounts when undiscovered: amounts are visible for enemy cargo scans, but labels remain `???`.
- Discovery triggers: advanced scan or encounter required (basic scan does not reveal surface minerals).
- Per-game discovery lives on `Player`, not `ServerRace`.
- Large-map exception: define the “rare” chance for a second deposit per secret resource.
  - Use 30% chance per resource (evaluated independently) on large maps.

**Implementation Phases**
1. Data model + migrations + fixtures for names.
2. Game generation placement + discovery tracking hooks.
3. Research and production cost integration.
4. UI masking and conditional visibility.
5. Messaging + tests.
