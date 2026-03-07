# Tech Rebalance Notes

## Scope Agreed Today

This is the current agreed rebalance scope from playtesting, not a full
category redesign.

## Electronics Pressure

`L6 Electronics` is carrying too much weight.

We want to spread that pressure out by moving or advancing a few items rather
than redesigning the whole tree at once.

## Agreed Moves

### Phased Disruptor

- move `Phased Disruptor` out of `Electronics`
- preferred destination:
  - `Metaphysics`, or
  - `Energy`
- implementation preference for this pass:
  - choose a single destination and keep the change small

### Planetary Disruptor Banks

- move `Planetary Disruptor Banks` to `Construction`
- add a blocking cross-category prerequisite tied to the category containing the
  related shipboard disruptor technology

For the current tree, that means the colony disruptor tech should not unlock
without some prior disruptor progress in the ship-tech category.

### Targeting Computer

- move `Targeting Computer` forward by at least one level
- intent:
  - make core fire-control improvement available earlier
  - reduce the amount of "must-have combat utility" stacked in `Electronics 6`

## Constraints

- keep the changes fixture-driven
- prefer category/level changes over mechanic rewrites
- preserve existing tech ids and names where possible
- if cross-category gating is added, keep it at the category-level prerequisite
  system already present in the codebase

## Follow-On Review

After this pass, review:

- whether disruptor progression still feels coherent
- whether `Electronics 6` is still overloaded
- whether the new `Construction` gate for colony disruptors feels fair in early
  defense play
