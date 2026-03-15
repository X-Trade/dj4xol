# Hull Tech Integration Plan

## Direction

Hull layouts should stay in `HullDesign`, but every `HULL` technology should
have one attached `HullDesign`.

`Technology` remains the source of truth for:

- research category
- research level
- display order
- enabled state
- description
- any extra gating data that still lives in `params_json`

`HullDesign` becomes the source of truth for:

- hull layout grid
- slot map
- hull thumbnail class
- cargo and fuel capacity
- offense and defense offsets
- mineral and special-resource hull costs

## Why This Shape

`Technology` is already the research-tree model and is used widely in unlock
logic. `HullDesign` is already the richer admin-side layout editor model.
Linking them keeps the research tree stable while letting the hull editor grow
into the future player-facing fitting system.

This also avoids stuffing layout JSON and slot state into the generic
`Technology` model.

## Immediate Setup

1. Add a one-to-one link from `HullDesign` to `Technology`, limited to
   `tech_type='HULL'`.
2. Backfill every existing `HULL` technology with a linked `HullDesign`.
3. Reuse an existing same-name prototype `HullDesign` when possible.
4. Create a fresh empty `HullDesign` when a `HULL` technology has no usable
   existing match.
5. Keep legacy unlinked prototype hull designs editable for now, but all new
   hull work should go through the linked flow.

## Hull Editor Behaviour

The Hull Designer should support both:

- editing an existing linked hull-tech + hull-design pair
- creating a new hull-tech + hull-design pair together

For new entries, staff should be able to either:

- attach to an existing unlinked `HULL` technology
- create a new `HULL` technology inline

The editor should also surface:

- the current linked hull tech
- unlinked `HULL` technologies available to attach
- linked/unlinked status in the hull list

## Data Sync Rules

When a linked hull is saved, the linked `HULL` technology should be updated so
its hull-related `params_json` values stay aligned:

- `max_cargo_capacity`
- `max_fuel`
- `hull_thumbnail_class`
- `offense_level`
- `defense_level`

Other technology params such as race gating should be preserved.

## Thumbnail Behaviour

When a `HULL` technology has a linked `HullDesign`, hull thumbnails should
prefer the hull design's `thumbnail_class` over the generic tech thumbnail
inference.

## Future Player Ship Design

This linkage prepares the next step:

1. player unlocks a `HULL` technology
2. that unlocks the linked `HullDesign`
3. player opens a fitting editor for that hull
4. player places unlocked component technologies into hull slots
5. the resulting player ship design becomes commissionable

That future layer should likely use a separate per-player ship design/loadout
model, rather than storing fitted parts directly on `HullDesign`.
