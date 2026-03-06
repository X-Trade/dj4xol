# Order Target Backend Cleanup

## Problem

`FleetOrders` currently stores most backend targets using direct foreign keys:

- `target_star_id`
- `target_fleet_id`
- `target_salvage_id`

But anomaly targets, and some generic object-target flows, still use
`target_short_id`.

This works today, but it mixes two different responsibilities:

- backend persistence / object identity
- frontend-facing URL and selection identity

`short_id` is the right identifier for links, URLs, and browser state. It is
not the ideal identifier for long-lived backend order storage.

## Why Change It

The current design is acceptable for MVP, but it creates avoidable ambiguity:

- `target_short_id` is polymorphic and must be resolved dynamically
- backend queries become less explicit than direct FK lookups
- delete / retarget logic has to special-case short-id-based orders
- validation is weaker because the database cannot enforce referential integrity
- the persistence model does not match the existing `target_star` /
  `target_fleet` / `target_salvage` pattern

In short: the backend should store backend object references, and the frontend
should translate to and from `short_id` at the boundary.

## Recommended Direction

Add `target_anomaly = ForeignKey(Anomaly, null=True, blank=True, related_name='+')`
to `FleetOrders` and migrate anomaly-targeted orders away from
`target_short_id`.

Longer term, if desired, the remaining generic-object use of `target_short_id`
can also be removed so order persistence becomes fully explicit.

## Non-Breaking Migration Strategy

The safe approach is staged, not a one-shot replacement.

### Stage 1: Add explicit anomaly target storage

- Add `target_anomaly` FK to `FleetOrders`
- Keep `target_short_id` in place temporarily
- Update `get_actual_target()` to prefer direct FKs first, including
  `target_anomaly`, then fall back to `target_short_id`

This makes the change backward-compatible immediately.

### Stage 2: Update write paths only

- In views and any CLI/admin order creation paths, resolve anomaly `short_id`
  to `Anomaly.id` once and store `target_anomaly`
- Continue accepting anomaly `short_id` from the frontend request layer
- Keep `target_short_id` populated only where still needed for compatibility

At this stage, user-facing behavior should not change at all.

### Stage 3: Backfill existing orders

- Add a data migration:
  - for each order with `target_short_id` matching an anomaly in the same game,
    set `target_anomaly_id`
  - leave orders untouched if they do not resolve cleanly
- Do not alter order position, repeat flags, coordinates, or other target fields

This preserves all existing queued orders.

### Stage 4: Update runtime cleanup logic

- Replace anomaly-retarget/delete queries that use `target_short_id` with
  `target_anomaly_id`
- Keep fallback support for `target_short_id` until the migration is fully
  deployed and verified

This avoids breaking already-queued legacy orders during rollout.

### Stage 5: Remove legacy dependency

Once all writes and existing rows are migrated:

- stop using `target_short_id` for anomaly targets
- consider whether any remaining generic object-target flow still requires it
- if not, remove or narrow the field in a later cleanup migration

## Important Compatibility Rules

To avoid breaking behavior during migration:

- do not change order execution order
- do not change repeat-order cloning behavior
- do not change coordinate fallback semantics
- do not change frontend request payloads yet
- do not remove `target_short_id` reads until all legacy rows are migrated

## Practical End State

Preferred steady state:

- frontend submits `short_id`
- view resolves it immediately
- order stores FK / UUID-backed backend reference
- message and map rendering convert objects back into `short_id` links only when
  formatting output

That keeps the storage model strict and the UI model flexible.
