# Report And Status Reference

This is the canonical developer-facing reference for report tiers, report
freshness, identity concealment, and the status/intel cues exposed through the
detail panel and Play CLI.

The goal is to keep four things aligned:

- report generation in `turn.py`
- cached report rendering in `objectdetails.py`
- player-facing web/detail output
- Play CLI summaries and `/detail` output

## Core Principles

- Map visibility is not the same thing as a report.
- Stars and anomalies can be visible on the map before any report exists.
- Fleets and salvage are not visible at all until scanners, contact, or a
  cached report reveal them.
- Non-owner intel should come from cached reports. The detail panel and Play
  CLI should not invent a weaker ad hoc "live" foreign-object view that
  downgrades richer cached intel.
- `ownership` is the highest report tier and means a full snapshot.
- `observed` is the thin contact tier. It exists mainly for no-scanners games
  and special minimal-contact cases. It must not be used as a synonym for
  `ownership`.
- `current` means the report was refreshed during the current generated turn.
  It does not mean "encounter" and it does not imply every section was freshly
  observed at the same detail level.

## Report Tiers

The current tier ladder is:

- `observed`
- `basic`
- `advanced`
- `encounter`
- `ownership`

Higher tiers override lower tiers for the same player/object report.

Intended meaning:

- `observed`
  Minimal cached contact report.
- `basic`
  Lowest scanner-game report tier.
- `advanced`
  Richer scanner-derived report.
- `encounter`
  Same-location report.
- `ownership`
  Full report.

## Visibility And Freshness

### Visibility Values

The detail panel and Play CLI use a small set of top-level visibility states:

- `visible`
  The object is map-visible but has no meaningful report yet. This is mainly
  for unexplored stars and anomalies.
- `current`
  The object has a report refreshed this turn.
- `report`
  The object is known from a cached report, but not freshly updated this turn.
- `last_known`
  A fleet report is stale and the fleet is no longer currently visible.

### Freshness Caveat

`current` is object-level freshness, not sectional freshness. A report may
still preserve richer older fields while refreshing weaker current facts. We
should revisit per-section freshness separately.

## Identity And Naming Rules

### Fleet Ownership Resolution

In scanners games, first detection of a foreign fleet on `basic` scanners does
not reveal the owner. A foreign fleet's owner becomes known only at:

- `advanced`
- `encounter`
- `ownership`

The same anonymity rule applies to `observed` fleet reports in no-scanners
games.

### Unknown Fleet Naming

Foreign fleets whose identity is not yet resolved should be named
`Unknown Fleet`.

That currently applies to:

- scanner-game `basic` fleet reports
- no-scanners `observed` fleet reports
- any derived display path that is presenting an unresolved foreign fleet

### Owner Relation

When owner identity is unresolved, Play CLI should emit:

- `owner_known: false`
- `owner_relation: unknown`

Once ownership is known, `owner_relation` should describe the owning player's
relationship to the viewing player:

- `own`
- `ally`
- `neutral`
- `enemy`
- `other`
- `abandoned`
- `unowned`

`stance` is the finer diplomatic label where applicable.

## Acquisition By Game Type

The important distinction is that scanners and no-scanners games use broadly
the same report ladder, but they generate those reports in different ways:

- scanners games:
  ranged scanners create scanner-tier reports, and contact upgrades that intel
  to `encounter`
- no-scanners games:
  contact generates the report in the first place, and the visiting fleet's
  scanner quality decides whether that contact yields `observed`, `basic`,
  `advanced`, or `encounter`

So the main difference is the trigger, not the meaning of the tiers.

### Scanners Games

- Basic scanners at range create `basic` reports.
- Advanced scanners at range create `advanced` reports.
- Same-location contact creates `encounter` reports.
- Encounter fleet cargo/capabilities depend on encounter scanner quality and
  cloak rules. If advanced scanners are present at the encounter, and the
  target is not effectively hidden by the relevant cloak rule, cargo and
  capabilities should be available.
- Allied/shared intel can grant `ownership` reports when the sharing policy is
  full enough to do so.
- Debug/manual "create report" should create `ownership`.

### No-Scanners Games

- Stars and anomalies can still be map-visible without reports.
- Reports are learned by visiting or otherwise directly observing objects.
- Contact is what generates the report; there is no separate ranged-scanner
  report flow.
- Visit tier depends on the visiting fleet's scanner quality:
  - no scanners: `observed`
  - basic scanners: `basic`
  - advanced scanners: `advanced`
  - exceptionally strong advanced scanners: `encounter`

## Object Payloads By Tier

The sections below describe the intended report contents. Implementation should
stay aligned with this reference even if field names or rendering helpers move.

### Stars

#### `observed`

- name
- position
- no owner
- no environment
- no population
- no minerals
- no infrastructure

#### `basic`

- everything in `observed`
- environment:
  - gravity
  - temperature
  - radiation
- habitability summary:
  - capacity
  - survivable / not survivable
- no owner
- no population
- no minerals
- no infrastructure

#### `advanced`

- everything in `basic`
- owner
- population
- mineral yields
- mineral inventories
- secret-resource concealment metadata where applicable
- no infrastructure

#### `encounter`

- everything in `advanced`
- infrastructure counts / presence only:
  - mines
  - factories
  - labs
  - colony scanner ranges
  - defenses
  - shipyards
  - cities
  - megacities
  - `has_administration`
  - `has_dyson_sphere`
- discovering secret resources at the star if they are present
- no derived colony-stat fields such as:
  - `factories_bp`
  - `labs_rp`
  - `administration_level`
  - `jobs_count`
  - `jobs_employment`
  - defense-force tooltip/stat lines

#### `ownership`

- everything in `encounter`
- full colony-stat fields:
  - `factories_bp`
  - `labs_rp`
  - `administration_level`
  - `jobs_count`
  - `jobs_employment`
  - any ownership-only defense/stat tooltip data

### Fleets

#### `observed`

- anonymised name: `Unknown Fleet`
- position
- motion summary:
  - heading
  - travel warp
  - warp advantage
- cloak state
- composition:
  - ship count
  - integrity
- no owner
- no cargo
- no capabilities

#### `basic`

- same information class as `observed`
- in scanner games this is the normal first-ranged-detection fleet report
- owner still hidden
- cargo still hidden
- capabilities still hidden

#### `advanced`

- everything from `basic`
- owner
- composition remains visible
- no cargo by default
- no capabilities by default

#### `encounter`

- everything from `advanced`
- cargo when encounter scanner/cloak rules allow it
- capabilities when encounter scanner/cargo rules allow it

#### `ownership`

- everything from `encounter`
- full fleet snapshot, including cargo and capabilities

### Salvage

Salvage does not have an owner, but its tiers should follow the same intent as
fleet tiers:

- `observed` matches the same visibility class as salvage `basic`
- `ownership` matches the same full-information class as salvage `encounter`

#### `observed` / `basic`

- name
- position
- total minerals
- type subject to concealment rules for ancient debris in scanner games
- no detailed inventory breakdown

#### `advanced` / `encounter` / `ownership`

- name
- position
- salvage type
- danger
- full mineral inventory breakdown

### Anomalies

Anomalies follow the same pattern:

- `observed` matches anomaly `basic`
- `ownership` matches the full anomaly information class

#### `observed` / `basic`

- name
- position
- anomaly type

#### `advanced` / `encounter` / `ownership`

- name
- position
- anomaly type
- danger
- description
- heading
- stability
- wormhole pairing data where relevant

## Special Situations

### Allied / Shared Intel

Where sharing rules call for the highest level of disclosure, allied/shared
intel should produce `ownership` reports for fleets and stars.

This is important for:

- annual shared-intel updates
- shared cloaked-fleet visibility when sharing rules permit it
- any view path that should mirror the shared report rather than re-derive a
  weaker local-contact view

### Trade Offers And Shared Report Offers

When a player is intentionally disclosing a specific owned object through a
contract or report trade, the recipient should receive an `ownership` report
for that object while the offer/report is active.

This is especially important for:

- offered fleets, so the recipient can evaluate cargo and capabilities
- offered colonies
- manually traded owned-object reports

### GIVE / Abandon

When a fleet is given away or abandoned, the previous owner should retain an
`ownership` fleet report so they keep the full snapshot from the moment of
transfer/loss.

### Invasion

When a colony changes hands via successful invasion:

- both victor and defender should retain `ownership` reports on the colony
- the defender should retain `encounter` intel on the invading fleet

The point is to preserve the colony-state snapshot at the moment ownership
changes.

## Secret Resources

`unknown_secret_resources` means:

- a secret resource is present on the star
- the viewing player has not yet discovered its identity

It is concealment metadata, not a visibility tier by itself.

## Play CLI Status And Intel Cues

The Play CLI should present the same actionable information a human player gets
from the detail panel, with extra textual context that a map-reading human
would otherwise infer visually.

### Canonical Top-Level Cues

Common top-level keys should remain stable and readable:

- `name`
- `x`
- `y`
- `visibility`
- `report_year`
- `report_tier`
- `object_type`
- `owner`
- `owner_known`
- `owner_relation`
- `stance`

Avoid redundant duplicates such as both `x` / `y` and a second combined
`position` string.

### Context Block

`context` is a compact situational summary. It should be explicit, not clever.

Canonical `context.location` values currently include:

- `visible_only`
- `star`
- `in_orbit`
- `in_transit`
- `stopped`
- `at_star`
- `deep_space`
- `last_known`

Useful context cues include:

- `in_transit`
- `idle`
- `effective_location`
- `last_known`
- `co_located`

### Intel Block

`intel` should say what is known, rather than forcing the reader to infer that
from omitted fields.

Examples:

- stars:
  - `owner_known`
  - `environment_known`
  - `population_known`
  - `resources_known`
  - `infrastructure_known`
- fleets:
  - `owner_known`
  - `name_known`
  - `composition_known`
  - `cargo_known`
  - `capabilities_known`
- salvage:
  - `type_known`
  - `total_known`
  - `inventory_known`
  - `danger_known`
- anomalies:
  - `type_known`
  - `stability_known`
  - `danger_known`
  - `description_known`

### Contacts And Available Actions

For richer `/detail` output, the CLI may include:

- `contacts`
  Presence cues such as hostile or allied co-located contacts.
- `available_actions`
  High-value owned-fleet action hints such as `can_transfer`, `can_refuel`,
  `can_bomb`, `can_colonise`, and `idle`.

These should be treated as situational aids, not hidden gameplay logic.

## Display Text Rules

- Use human-readable display text where possible in player-facing output.
- Keep machine-useful raw codes only when they add value, for example companion
  `*_code` fields.
- Example:
  - display: `Black Hole`
  - code: `BLACK_HOLE`

## Summary

The intended model is:

- map visibility separate from reports
- `observed < basic < advanced < encounter < ownership`
- `ownership` means full report
- `observed` means thin contact report
- `current` means refreshed this turn
- unresolved foreign fleet identity means `Unknown Fleet`
- CLI/status output should make knowledge and uncertainty explicit
