# Combat And Bombardment Damage Model

This note is a developer reference for the current combat, colony defensive-fire,
and bombardment damage model.

## Scope

- Space combat between fleets
- Colony defensive fire against fleets and bombardment groups
- Bombardment penetration and damage scaling
- How displayed `integrity` relates to actual ship losses

Core arithmetic lives in:

- `dj4xol/combat_rules.py`
- `dj4xol/bombardment_rules.py`
- `dj4xol/turn.py`

## Core Count Model

Ship count is no longer flattened to a tiny ceiling. It now uses a small-fight
linear curve and a large-fight square-root curve:

- counts `1..3` stay linear
- counts above `3` are softened with `normalize_ship_count`

Combat tech and race multipliers scale count before softening.

That means:

- a small fight still feels intuitive
- large fleets stay stronger, but with diminishing returns
- offense and defense matter as force multipliers on count, not as a tiny bonus after count has already saturated

## Combat Strength

For fleet-vs-fleet combat we calculate two strengths per fleet:

- attack strength
- defense strength

Both use the same softened-count model, but attack uses fleet offense tech and
defense uses fleet defense tech.

Integrity reduces both strengths through `integrity_factor`, so damaged fleets
hit less hard and absorb less punishment.

Per-player strengths are the sum of that player's fleets at the location.

## Side Damage

Combat damage is not a fixed split by ship-count share anymore.

Each side receives a damage percent derived from opposing attack pressure versus
its own defense pressure:

- `damage = scale * log2(1 + opponent_attack / own_defense)`

This keeps damage responsive to mismatches without exploding linearly.

## Fleet Durability Pool

Displayed fleet integrity remains `0..100`, but internally combat now treats a
fleet as having a defended durability pool.

Definitions:

- displayed integrity total = `ship_count * integrity`
- current defended pool = `ship_count * integrity * defense_multiplier`
- full defended capacity = `ship_count * 100 * defense_multiplier`

Important implication:

- a `10` ship fleet at `100%` integrity has `1000` displayed integrity points
- if its defense multiplier is `64x`, its full defended pool is `64,000`

## Applying Damage To A Fleet

When a fleet takes `damage_percent` in a round:

1. compute the fleet's current defended pool
2. compute the fleet's full defended capacity
3. burn `full_capacity * damage_percent` from the current pool
4. cap that burn to the fleet's remaining current pool
5. convert the remaining pool back into whole surviving ships plus displayed integrity

This is why a fleet can lose multiple ships in a single round and still end up
with survivors at high displayed integrity.

Example:

- `10 ships @ 100% integrity`
- `defense_multiplier = 1`
- `damage_percent = 90`

Result:

- `1 ship @ 100% integrity`
- `9 ships lost`
- `900` aggregate integrity points lost

## Meaning Of `integrity_lost`

`integrity_lost` in combat and defensive-fire summaries is aggregate displayed
integrity loss across all affected ships, not "the final integrity bar moved by
this many points on one ship."

So values above `100` are valid and expected for multi-ship fleets.

## Colony Defensive Fire

Colony defensive fire now uses the same attack-vs-defense pressure model as
fleet combat.

The colony contributes a static defense force built from:

- effective defenses
- colony defense tech
- fixed-homeworld bonus when applicable

The target fleet or bombardment group contributes:

- attack strength for the confrontation
- defense strength for damage resistance

The resulting damage is then applied through the same fleet durability-pool
conversion described above.

This keeps defensive fire and fleet combat aligned.

## Bombardment Penetration

Bombardment damage and colony defensive fire are related but separate:

- colony defensive fire is resolved with the combat damage pipeline
- bombardment damage to the world is resolved with `bombardment_damage_k`

Bombardment uses:

- ship count
- bomb type multiplier
- luck roll
- race bombardment multiplier
- fleet `defense_level` as the bombardment tech factor
- colony defenses as the opposing pressure

Important design choice:

- bombardment penetration still keys off fleet `defense_level`
- bombardment does not use fleet `offense_level` for penetration

That matches the intended interpretation that bombers need defensive resilience
to survive and punch through colony defensive fire.

## Combined Bombardment

When multiple fleets from the same player bombard together with the same bomb
type at the same star:

- bombardment damage is combined
- colony defensive fire is resolved against the group
- returned damage results are still tracked per fleet

## Public Help

The public player-facing summary for this system lives in:

- `dj4xol/templates/dj4xol/help_space_combat.html`

Keep that page high-level. This document is the place for exact developer
semantics and the meaning of aggregate damage values.
