# Technology Rebalancing Plan

## Goals

- Keep most technology classes spread across roughly two research categories on
  average, while preserving narrative fit.
- Reduce early-game Metaphysics impact so the category feels exotic and late
  rather than a dominant early path.
- Use category-level prerequisites (not per-item) to gate access to late- and
  end-game tiers and prevent single-category rushing.
- Maintain Infrastructure as a special case that can span more categories
  because it is applied differently (colony tech mirroring fleet tech types).

## Current Observations (fixtures)

- Metaphysics and Electronics contain significantly more technologies than
  Energy, Materials, or Construction.
- Several early Metaphysics items create a strong early-game payoff that
  undermines the “exotic/late” feel.
- Some items that are primarily mechanical or fire-control systems are not
  classified as such.

## Late/End-Game Inventory (L17/L19/L24 focus)

This list is a quick reference for the late/end-game tiers that will likely
receive the first wave of cross-category gating.

- **Construction**
  - L16: City Hull
  - L16: Trans-Spatial Defense Matrix (Infrastructure)
- **Electronics**
  - L17: Pulsar Cannon
  - L19: Scanner Array XII / Colony Scanner Array XII
  - L26: Scanner Array XIV
- **Energy**
  - L19: Micro-Singularity Gun
- **Materials**
  - L18: Beamed Warhead Delivery Torpedo
- **Metaphysics**
  - L17: Prototype Wormhole Drive
  - L18: Wormhole Drive
  - L19: Nova Bombs
  - L22: Advanced Wormhole Drive
  - L24: Scanner Array XIII / Colony Scanner Array XIII
  - L26: Wormhole Drive MkIII

## Already Applied Changes

- `Maneuvering Jets` moved to `MECHANICAL` and the `CONSTRUCTION` category.
- `Tractor Beam` moved to new `ELECTRICAL` tech type.
- `Targeting Computer` moved to new `ELECTRICAL` tech type.
- Added `ELECTRICAL` tech type to `Technology.TECH_TYPE_CHOICES`.
- `Trans-Spatial Defense Matrix` moved to L17.

These changes intentionally alter stacking behaviour because tech effects are
selected by tech type.

## Proposed Fixture / Gameplay Changes (Rebalancing)

### 1) Reduce early Metaphysics density (L0–L9)

Move early Metaphysics items into more grounded categories:

- Propulsion:
  - `Adaptive Navigation Computers` (L2) → `ELECTRONICS`
  - `Phase-Coupled Warp Frames` (L5) → `ENERGY`
  - `Inertial Shear Dampers` (L9) → `ENERGY`
- Shields:
  - `Deflector Shield` (L2) → `MATERIALS`
  - `Phased Shield Array` (L6) → `MATERIALS`
- Scanners:
  - `Scanner Array III` (L5) → `ELECTRONICS`
  - `Scanner Array V` (L8) → `ELECTRONICS`
- Colony scanners:
  - `Colony Scanner Array IV` (L6) → `ELECTRONICS`
  - `Colony Scanner Array VII` (L10) → `ELECTRONICS`

Result: Metaphysics becomes sparse before L10, aligning with the “exotic”
positioning.

### 2) Keep Metaphysics strong in mid/late game

Metaphysics retains/receives the most exotic items:

- `Trans-Spatial Shielding` (L10)
- `Null Field Generator` (L15)
- `Null-Phase Transit Geometry` (L12)
- Wormhole drives (L17+)
- `Nova Bombs` (L19)
- High-tier scanners (L12+)
- High-tier colony scanners (L12+)

### 3) Mid-game adjustment

- `Smart Bombs` (L10) moved to `ELECTRONICS` (guided systems).

## Category-Level Prerequisites (Gating)

### Principle

Gate research **by category level**, not by individual technology items. This
keeps UI/simple logic and prevents rushing later items within a category once a
single level is unlocked.

### Current Requirements (from design direction)

- Keep gating **light-touch** for now.
- End-game levels should require mid- and late-game levels from other
  categories.
- Late-game levels should require mid-game and late-game levels from other
  categories.
- Prerequisite levels should always be lower than the requiring level.

### Behaviour

- A category level cannot be completed unless all its prerequisites are met.
- The prerequisite should be shown in:
  - Research screen “Next Level” detail
  - Technology directory entries (per category level)

### Initial Gate Set (light-touch)

Late-game gates (require mid + late):

- **Metaphysics L17** requires:
  - Electronics L12
  - Energy L14
- **Construction L17** requires:
  - Materials L12
  - Metaphysics L13

End-game gates (require mid + late):

- **Metaphysics L19** requires:
  - Materials L16
  - Energy L16
  - Electronics L12

Early/mid gates (intro mechanic, minimal restriction):

- **Electronics L8** requires Energy L5
- **Materials L8** requires Construction L6
- **Energy L12** requires Materials L9
- **Construction L12** requires Materials L10
- **Construction L4** requires Materials L3

### Progression Bands (used for gating)

- L0–3 beginner
- L0–5 early game
- L5–12 mid game
- L13–18 late game
- L19–26 end-game

### Implementation Outline (for later)

- Add a `ResearchLevelPrerequisite` model:
  - `category`, `level`, `requires_category`, `min_level`
- Enforce in `research._advance_research_row_with_requirements`.
- Surface in `build_research_screen_data` and help/tech directory.

## Open Decisions

- Exact prerequisite thresholds for L17/L19/L24 once end-game tuning is final.
