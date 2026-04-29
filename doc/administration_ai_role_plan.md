# Administration AI Role and Strategy Plan

This document captures the next round of Micromanager/Administration AI goals agreed after live playtesting. The broad aim is to move the AI from a single generic colony planner toward role-aware colony development, tiered threat and terraforming judgement, and stronger L5 empire behavior.

## Goals

- Classify colonies by environmental, resource, strategic, and threat factors.
- Use those classifications to steer Administration production priorities.
- Keep L3 Administration simple and mechanical, while L4+ uses stronger weighting.
- Preserve the existing technology tier/unlock system.
- Keep L5 AI Micromanager behavior the most optimized version.
- Validate behavior with focused unit tests and long-running AI tests.

## Colony Role Classification

Roles should be scored or multi-label rather than mutually exclusive. A colony can be both `mining` and `frontier`, or `eden` and `production`.

Suggested implementation shape:

```python
classify_colony_role(player, star, context=None)
score_terraform_roi(player, star, role, tier, context=None)
score_frontier_threat(player, star, tier, context=None)
```

The helper should live in a pure rules module such as `dj4xol/colony_ai_rules.py`, or in `micromanager_rules.py` if it remains small. Prefer pure Python inputs and simple return values so unit tests do not require turn generation.

## Role Definitions

### Mining World

Purpose: extract minerals, export excess materials, support enough local industry to keep mines productive.

Signals:

- Colony is survivable.
- At least one resource factor/yield is greater than 56%.
- Habitability may be poor; poor habitability does not disqualify mining worlds as long as the world is survivable.
- High mineral value should remain important even when population growth is weak.

Behavior:

- Prioritize mines strongly.
- Build enough factories/support to operate mines.
- Avoid overbuilding cities/labs unless it is also an eden or production world.
- Later logistics should collect minerals from these worlds.

### Eden World

Purpose: population engine, high-value core world, logistics destination, colonist source.

Signals:

- High habitability.
- Good long-term population capacity.
- Often useful even with mediocre minerals.

Behavior:

- Prioritize population growth, cities/megacities, labs, and healthy defenses.
- Prefer imports of mined materials.
- Later logistics should move excess colonists outward and receive minerals.
- Long-term role as colony ship source and resupply hub.

### Production/Forge World

Purpose: industry, shipbuilding, and major project construction.

Signals:

- Good habitability or sufficient population.
- Strong mineral flow, either local or imported.
- Enough factories/shipyards to justify further industrial investment.

Behavior:

- Prioritize factories, shipyards, defenses, and major projects.
- Can be a Dyson Sphere candidate at L5 if capacity and unlocks support it.

### Research World

Purpose: lab-heavy high-habitability colony, usually with weaker local minerals.

Signals:

- High habitability.
- Weak or moderate mineral factors.
- Safe enough to justify lab investment.

Behavior:

- Prioritize labs, population support, imported minerals, and moderate defenses.
- Deprioritize labs once all research fields are maxed out.

### Frontier World

Purpose: border defense and staging near other players.

Signals:

- Nearby other-player-owned colony.
- Stronger score when nearby player stance is cold or hostile.
- Stronger score when the colony is valuable, exposed, or far from core support.

Behavior:

- Increase defenses.
- Seed or raise shipyards earlier.
- Avoid treating the colony as a peaceful city/lab sink.

### Terraform Candidate

Purpose: improve a valuable world whose current habitability limits growth or productivity.

Signals:

- Habitability is low or near environment edges, but the world has value.
- Value can come from minerals, high capacity, eden potential, production potential, current population, or strategic position.
- Mining worlds can still be terraform candidates if poor habitability blocks workforce growth.

Behavior:

- Add terraforming orders when ROI is high.
- Remove terraforming orders once that environment factor is close to ideal.
- Use stronger ROI scoring at L4+ than L3.

### Marginal Outpost

Purpose: minimal useful presence.

Signals:

- Survivable but weak habitability.
- Weak mineral factors.
- Low strategic value.

Behavior:

- Avoid deep queue investment.
- Maintain minimal safety/support.
- Do not compete heavily with mining, eden, frontier, or production worlds.

## Administration Tier Behavior

### L3 Administration

L3 should use simple, mechanical rules.

Capabilities:

- Basic role classification.
- Simple mining/eden/marginal distinction.
- Basic terraform ROI.
- Basic threat-aware defense.

Threat behavior:

- If another player's colony is nearby, nudge defenses upward.
- If that player has cold or hostile stance, apply a stronger but still simple defense nudge.
- Do not require detailed fleet strength analysis.

Terraform behavior:

- Prefer terraforming when habitability is poor and the world is valuable.
- Use coarse thresholds rather than multi-factor strategic planning.

### L4 Administration

L4 should use stronger weighting and better context.

Capabilities:

- Stronger role-aware scoring.
- Better terraform ROI from habitability delta, resource quality, capacity, current population, infrastructure, and strategic value.
- Stronger frontier defense weighting from distance and diplomatic stance.
- Existing logistics dispatch can be improved lightly, but full logistics redesign is not required in this pass.

Threat behavior:

- Cold or hostile nearby colonies should meaningfully raise defense and shipyard priority.
- Friendly or neutral neighbors should have smaller or no defense pressure.

Terraform behavior:

- Terraform valuable worlds more aggressively.
- Avoid over-terraforming marginal worlds.

### L5 AI Micromanager

L5 should consume the same role and context signals but optimize more aggressively.

Capabilities:

- Best production priorities.
- Stronger empire-level logistics.
- Dedicated expansion and exploration planning.
- Dyson Sphere project awareness.
- Hostile expansionist bombardment targeting.

## Terraform ROI

Terraform ROI should use:

- Current habitability.
- Distance from ideal environment center.
- Expected habitability after terraforming.
- Colony role.
- Mineral quality.
- Capacity/population potential.
- Current population and infrastructure.
- Frontier/strategic value.

Important behavior:

- Poor-habitability mining worlds should still mine if survivable.
- Terraforming a valuable mining world can be worthwhile if habitability blocks workforce growth.
- High-habitability eden worlds should not waste terraforming orders once already close to ideal.
- Marginal worlds should rarely win terraform priority unless strategic context changes.

## Threat-Aware Defense

Threat scoring should start simple and become stronger by tier.

Inputs:

- Distance to other-player colonies.
- Diplomatic stance.
- Known hostile or cold relationship.
- Colony value from role score.
- Existing defenses and shipyards.

L3 behavior:

- Nearby foreign colony creates a defense nudge.
- Cold/hostile stance creates a larger defense nudge.

L4+ behavior:

- Defense/shipyard priority scales by distance, stance, and colony value.
- Frontier mining and eden worlds should not be left soft.

## Exploration Ships

Exploration should be especially important early in the game and rarer later.

Goals:

- Improve report coverage and habitability knowledge.
- Discover distant eden, mining, and terraform candidate worlds.
- Avoid sending all fleets only to already-known nearby colonies.

Behavior:

- Early game: aggressively create exploration routes when report coverage is low.
- Mid game: reduce exploration if enough colonization targets are known.
- Late game: exploration becomes rare and targeted at remaining unknown clusters.
- Use multi-leg journeys, not single-star trips.
- Route waypoints should try to catch as many worlds as possible in scanner range.
- Prefer unknown or poorly reported regions.
- Prefer clusters that are likely to reveal valuable colonization targets.

Suggested helpers:

```python
score_exploration_need(player, context)
select_exploration_waypoints(player, fleet, candidate_stars, sensor_range, max_legs)
```

## Dedicated Expansion Improvements

Expansionist AI should eventually have a dedicated colony ship process.

Goals:

- Build and dispatch colony ships intentionally.
- Use reports and role scores to select high-value targets.
- Avoid wasting colony ships.
- Expand faster without destroying early economic bootstrap.

## Duplicate Colony Ship Prevention

Problem: expansionist/micromanager AI can send colony fleets to stars that already have a friendly colony fleet en route. If the first fleet colonizes the target, later fleets can be wasted or lost.

Rules:

- Before dispatching a colonization fleet, collect stars with inbound friendly colonization orders.
- Do not dispatch another colonization fleet to the same target.
- Still allow extra colonists, defense stock, logistics fleets, or other non-colonization missions to that target.

Suggested helpers:

```python
friendly_colonization_targets_in_flight(player)
can_dispatch_colony_fleet_to(player, star)
```

## Dyson Sphere Awareness

This is L5 AI behavior. Treat Dyson Sphere construction as a strategic project rather than an ordinary production order.

Candidate signals:

- Dyson Sphere is unlocked.
- Colony is a homeworld, eden world, or production/forge world.
- Colony can support multiple billions of population or is clearly growing toward that scale.
- The colony can reserve DS job headroom.
- Secret resource requirement is known and not already present.

Behavior:

- Reserve enough job headroom so the DS can be built without pushing employment over about 70%.
- Send a logistics fleet to fetch the secret resource needed for DS construction.
- Do not fill all job capacity with factories/cities if a DS project is selected.
- Prefer safe, high-value worlds for DS projects.

Suggested helper:

```python
score_dyson_candidate(player, star, role, tech_context, logistics_context=None)
```

## Expansionist Bombardment

Expansionist AI should consider bombing other-player-owned worlds when strategically appropriate.

Candidate signals:

- Target is owned by another player.
- Target is habitable/survivable for the expansionist player.
- Stance toward the owner is cold or hostile.
- Fleet has bombs and can reach the target.
- Target has value as eden, mining, frontier, or production world.

Guardrails:

- Do not bomb allies.
- Avoid neutral targets unless explicitly allowed later.
- Avoid uninhabitable or low-value worlds.
- Avoid obviously suicidal attacks when known defenses are overwhelming.

Suggested helper:

```python
score_bombardment_target(player, star, report, stance_context, fleet_context=None)
```

## Test Plan

Use unit tests first, then long-running validation.

### Unit Tests

Role classification:

- Poor-habitability, high-resource, survivable world classifies as mining.
- High-habitability, weak-mineral world classifies as eden/research.
- High-resource hostile-border world classifies as mining and frontier.
- Poor-habitability, strong-resource world gets terraform candidate score.
- Poor-habitability, weak-resource world stays marginal.

Planner behavior:

- L3 mining world prioritizes mines despite poor but survivable habitability.
- L3 frontier world includes defenses earlier than a comparable safe world.
- L4 hostile frontier defense pressure beats city/lab greed.
- L4 high-ROI terraform candidate gets terraform before generic support.
- Eden world does not get treated as a mining outpost just because one yield is decent.

Fleet behavior:

- Existing inbound colony fleet prevents duplicate colonization dispatch.
- Inbound logistics or defense fleet does not block colonization dispatch.
- Early exploration creates multi-leg routes.
- Later exploration becomes less frequent as report coverage improves.
- Expansionist bombing selects cold/hostile habitable worlds and skips allied worlds.

Dyson behavior:

- L5 homeworld/eden/production world reserves job headroom for DS.
- L5 dispatches a logistics fetch for the secret resource.
- Non-candidate worlds do not starve normal production for DS.

### Long-Running Tests

Create seeded archetype maps:

- One eden world.
- One poor-habitability rich mining world.
- One marginal world.
- One frontier world near another player.
- One strong DS candidate if testing L5 strategic projects.

Run 60 to 100 years and assert trends rather than exact order sequences:

- Mining world builds more mines than eden/marginal worlds.
- Eden world grows population/cities/labs more than mining/marginal worlds.
- Frontier world builds more defenses than comparable safe colonies.
- Terraform candidate receives terraforming orders when unlocked.
- Marginal world does not consume huge queues.
- Early exploration increases report coverage.
- Exploration dispatch frequency drops later.
- Duplicate colony dispatches do not occur.
- Expansionist reaches viable colony counts without wasting colony fleets.

## Suggested Implementation Order

1. Add colony role/context helper and unit tests.
2. Add terraform ROI and basic L3/L4 role-aware production scoring.
3. Add L3/L4 threat-aware defense scoring.
4. Add duplicate colony dispatch prevention.
5. Add exploration need scoring and multi-leg route selection.
6. Add L5 Dyson Sphere strategic project awareness.
7. Add expansionist hostile bombardment targeting.
8. Add long-running archetype tests and tune thresholds.

