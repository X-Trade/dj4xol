# Performance Notes: Visibility, Starmap, and Play CLI

## Context

Recent playtesting suggests the main game screen and Play CLI are responding
more slowly than expected.

This note records the likely hotspots identified from code inspection and a
pragmatic direction for a later optimization pass.

## Likely Hotspots

### Repeated Scanner Source Computation Per Request

The main game view currently rebuilds scanner-source state multiple times during
the same page load:

- `DetailBuilder`
- `StarMap`
- scanner-circle overlay construction

All of these call `get_scanner_sources_for_player()` separately.

That means one page render repeats the same fleet/colony scanner aggregation
several times.

###+ Fleet Visibility Filtering Is Python-Heavy

The starmap currently:

- loads all fleets in the game
- then filters them in Python by scanner visibility

This is roughly proportional to:

- `number of fleets in game`
- times `number of scanner sources for player`

That is acceptable at small scale, but it will get noticeably slower as fleet
counts grow.

### Play CLI List Commands Overuse `DetailBuilder`

Several Play CLI list commands currently instantiate `DetailBuilder` once per
object:

- `/reports`
- `/fleets all`
- `/fleets other`
- `/salvage`
- `/anomalies`

That is expensive because `DetailBuilder` is designed for full detail panel
assembly, not bulk summaries.

Each object can trigger:

- short-id resolution
- visibility checks
- report lookups
- location-presence checks
- payload formatting that list views do not actually need

This is the most likely reason the Play CLI feels slower.

### Repeated Visibility Queries Inside `DetailBuilder`

`can_view_object()` currently does fresh per-object checks such as:

- player fleet at location
- player star at location
- cached report lookup

Those checks are correct, but they are repeated many times and should be based
on precomputed turn/request state instead.

### Secondary Cost: Repeated Short-ID Type Lookup

`process_selected()` checks stars, fleets, salvage, and anomalies separately by
`short_id`.

This is not the biggest issue, but it is still unnecessary repeated work.

## Important Observation

Most of the expensive state being computed is turn-stable.

For a given player during a given game year, the following do not normally
change during page views:

- scanner sources
- which fleets are currently visible
- which salvage/anomalies/stars are known through reports
- report years / report tiers
- star owner visibility at known locations
- rendered starmap object set for that player

In other words:

- the starmap does not change during the turn
- visibility filters do not need to be recomputed on every page view or Play
  CLI request

This suggests caching should be driven by turn boundaries, not just request
boundaries.

## Recommended Direction

### 1. Introduce a Shared Visibility Context

Build a lightweight `visibility context` object for:

- one `game`
- one `player`
- one `year`

It should contain precomputed turn-stable data such as:

- scanner sources
- visible fleet ids
- visible fleet summaries
- reported salvage ids
- reported anomaly ids
- star report tiers
- report-year lookup by `(target_type, target_id)`
- owned/present coordinates for current-detail visibility

This context can be reused by:

- `StarMap`
- `DetailBuilder`
- Play CLI list commands
- any map-selection or detail API helpers

That removes repeated DB work and makes visibility rules consistent in one
place.

### 2. Cache Turn-Stable Visibility State

Because visibility does not normally change mid-turn, the visibility context can
be cached per:

- `game id`
- `player id`
- `game year`

Possible invalidation rule:

- if `game.year` changes, recompute

This is simple and matches the game model.

Potential storage options:

- in-memory cache for a single-process deployment
- Django cache backend for multi-process deployments
- precomputed DB rows if needed later, though that is probably unnecessary at
  first

### 3. Cache Rendered Starmap Fragments

The rendered map itself is also mostly turn-stable per player.

So the player-specific starmap HTML could be cached by:

- `game id`
- `player id` (or spectator/admin mode)
- `game year`
- `dest_mode` if link rendering differs

That would avoid rebuilding:

- fleet visibility filtering
- salvage visibility filtering
- large HTML strings

The main caution is selection state:

- the map object set is cacheable
- selection highlighting or destination-mode link behavior may need a small
  dynamic wrapper or separate cache key

### 4. Stop Using `DetailBuilder` for Bulk Play CLI Summaries

The Play CLI should not use full detail-panel assembly for list commands.

Instead, list commands should read from:

- cached visibility context
- cached reports
- bulk-loaded model rows

Then build only the fields they need.

Examples:

- `/reports` only needs name, report year, owner, location, class, subclass
- `/salvage` only needs known salvage plus total minerals if known
- `/fleets all` only needs known fleets, owner, visibility, ship count if known

This should materially reduce CLI latency.

### 5. Use SQL Bounding Boxes for Fleet Visibility Candidates

For current fleet visibility:

- do not fetch every fleet in the game
- instead, build a union of scanner-range bounding boxes in SQL
- fetch only candidate fleets
- then do exact circle-distance checks in Python

This keeps correctness while avoiding full-game Python scans.

### 6. Reduce Per-Object DB Lookups in `DetailBuilder`

`DetailBuilder` should accept precomputed visibility/report state so that:

- `can_view_object()` becomes set/dict lookup based
- `process_selected()` can use a shared short-id map when available
- report-year access does not require repeated query calls

## Suggested Implementation Order

### First Pass

- add a shared per-request visibility context
- pass it into `DetailBuilder`, `StarMap`, and scanner-circle helpers
- remove repeated calls to `get_scanner_sources_for_player()`

This is the safest low-risk improvement for the main game screen.

### Second Pass

- rewrite Play CLI list commands to use bulk summaries instead of `DetailBuilder`

This is likely the biggest win for Play CLI responsiveness.

### Third Pass

- add per-turn caching for:
  - visibility context
  - rendered starmap HTML

This should provide the best end result once correctness is locked in.

## Design Principle

Visibility in this game is primarily a turn-resolution product, not a live UI
computation.

So the code should move toward:

- computing visibility once per turn or once per player-year
- reusing it across page loads and API calls
- treating UI rendering as a consumer of known turn state, not the place where
  visibility is rediscovered repeatedly

That should improve:

- main game page responsiveness
- Play CLI responsiveness
- consistency between web UI and CLI visibility rules
- future maintainability of report/scanner logic
