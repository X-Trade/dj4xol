# Spectator Mode Plan

## Goals
- Allow accounts to **spectate public games** they are not playing.
- Spectators **cannot later join** the game they spectated (explicit consent).
- Spectator UI shows **starmap + detail panel only**, read-only.
- Spectator detail level is **basic scan** for all objects (global visibility, no exploration).
- **Admins** see full report detail while spectating.
- Secret resource labels respect **account-level discovery** (unknown shown as `???`).
- If already a spectator, the “View” button jumps directly to spectator map.

## UX Flow
1. Games list shows **View** button for public games where:
   - user is authenticated,
   - user is **not** already a player,
   - user is **not** already a spectator (for button routing only).
2. Clicking **View**:
   - If no spectator record: show consent form.
   - If spectator record exists: go directly to spectator map.
3. Consent form:
   - Text: “If you spectate this game, you will never be allowed to play it.”
   - Confirm button (creates spectator record).
4. Spectator map:
   - Main starmap + detail panel only.
   - No order panels, no production or management actions.
   - Detail panel data is **basic scan tier** for all objects.
   - Player names are visible on stars/fleets.
   - Admin users see **full detail** (equivalent to encounter/owner detail).

## Data Model
Add a new model:
- `Spectator`
  - `game` (FK Game)
  - `account` (FK Account)
  - `created_at`, `consented_at`
  - Unique constraint: `(game, account)`

Purpose: enforce “cannot join after spectating” and allow fast lookup for routing.

## Permissions / Access Rules
- `join_game` must block if a Spectator record exists for `(game, account)`.
- Spectator map view only accessible if:
  - account has Spectator record OR account is admin (admin can view any game).
- Spectators are **not** Players; do not create Player row.

## Starmap/Detail Behavior
### Spectator detail tier
Implement a “forced report tier” for spectators:
- Non-admin spectators: **basic** tier for all objects.
- Admin spectators: **full** tier (equivalent to current detail for owners or encounter).

### Required DetailBuilder changes
- Add optional parameters:
  - `forced_report_tier` (e.g., `'basic'`)
  - `is_admin_view` (bool)
- If `forced_report_tier` is set:
  - Bypass player/ownership gating.
  - Render detail using `_build_detail_from_report`-style data assembled from objects using that tier.
  - For basic tier (spectators):
    - Star: name, location, environmentals, **player name**, **population**, **yields**, **surface minerals**.
    - Fleet: name, location, **player name**, **cargo/inventory** (no composition/capabilities).
    - Salvage: name, location only.
    - Anomaly: name, location, **type**.
  - Admin view uses full detail (current owner/encounter detail builder path).

## Views & Templates
### New views
- `spectate_game_confirm(request, game_short_id)`
  - GET: show consent form.
  - POST: create Spectator record then redirect to spectator map.
- `spectate_starmap(request, game_short_id)`
  - Build starmap with spectator detail rules.

### Existing views updates
- `games` list: add `View` link alongside `Join` for eligible games.
- `join_game`: block if spectator record exists.

### Templates
- New template: `spectate_confirm.html` (copy join-game style header/structure).
- New template: `spectator_starmap.html` (reuse starmap shell but hide order panels).
- Update `games.html` to show View button with correct routing.

## Starmap Rendering
- Continue using `StarMap` for layout.
- Detail builder gets `player=None` and `forced_report_tier='basic'` for spectators.
- Admin path: `player=None`, `is_admin_view=True`.

## Play CLI
- No changes; spectator mode is web-only.

## Tests
### Model
- `Spectator` unique constraint enforced.

### View/permission tests
- Spectator consent creates record.
- Attempt to join after spectating -> forbidden.
- “View” route goes to confirm if no record, direct to map if record exists.
- Spectator map requires spectator record unless admin.

### Detail behavior tests
- Spectator detail is basic tier:
  - Stars show environmentals + player name.
  - Fleets show presence + player name (no ship_count/cargo).
  - Salvage shows no mineral totals.
  - Anomalies show type but no stability.
- Admin spectator sees full detail (stability/cargo/etc).

## Migration/Deployment Notes
- Add migration for `Spectator` model + unique constraint.
- No data backfill required.

## Open Decisions (confirm before coding)
- (Resolved) Basic spectator reports include star yields/inventory/population and fleet cargo.
