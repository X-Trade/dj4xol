# Diplomatic Contracts V1

This document defines the first implementation of drafted diplomatic
messages, negotiated contracts, and contract-linked diplomatic alerts for
the Diplomacy screen.

## Goals

- Let players send structured diplomatic proposals, requests, and demands.
- Support a small set of fulfilment-tracked clause types.
- Surface incoming diplomacy prominently in web, Play CLI, and email
  rollups until it is handled.
- Keep the rules deterministic and compatible with existing turn
  processing, stance staging, reports, and inventory systems.

## High-Level Flow

1. Player opens the Diplomacy screen and selects an encountered race.
2. Player opens a draft wizard from that race detail.
3. Player composes one contract with:
   - temperature: `propose`, `request`, or `demand`
   - condition connector: `in exchange for` or `or else`
   - one clause from sender side
   - one clause from recipient side
   - deadline in years, default `24`
   - optional deadline extension on acceptance
4. Recipient sees a diplomatic-priority alert pinned until handled.
5. Recipient may:
   - accept
   - decline
   - counter
6. Accepted contracts track fulfilment until completed, expired, or
   revoked.

## Contract States

- `DRAFT`
- `SENT`
- `ACCEPTED`
- `FULFILLED`
- `DECLINED`
- `COUNTERED`
- `EXPIRED`
- `REVOKED`

Rules:

- `REVOKED` is only allowed while the contract is unanswered.
- `EXPIRED` occurs when the deadline passes without the required response
  and fulfilment.
- `COUNTERED` closes the previous proposal and creates a replacement
  contract.

## Clause Model

Each side of a contract has exactly one clause. No clause stacking in V1.

Temperature is presentation only. It sets the diplomatic mood of the
message, while the separate condition connector determines whether the
sender is offering an exchange or threatening an `or else` consequence.

Supported clause types:

- `NOTHING`
- `TECHNOLOGY`
- `STANCE`
- `RESOURCE_TO_WORLD`
- `RESOURCE_ON_GIVEN_FLEET`
- `FLEET_BY_SHIP_COUNT`
- `SPECIFIC_FLEET`

### `NOTHING`

No gameplay effect. Used for one-sided proposals or for the V1
`or else nothing` placeholder.

### `TECHNOLOGY`

- The named technology must already be unlocked by the giving player.
- Grant is permanent once awarded.
- Grant bypasses ordinary research and race-type tech gating by creating
  an explicit player technology entitlement.
- Tech-for-tech exchanges fire immediately on acceptance.

### `STANCE`

- Represents a pending stance change by one player toward the other.
- It is posted only when the relevant obligation is fulfilled.
- Once posted, it follows the normal pending-stance system and becomes
  effective at the next turn generation.

### `RESOURCE_TO_WORLD`

- Requests a bundle of minerals, colonists, and/or known secret resources.
- Delivery to any owned star of the requesting player counts.
- The draft may include a suggested destination colony as a courtesy only.
- Suggested colony is not required for fulfilment.
- The UI should warn when the relationship is below neutral/warm because
  routine transfers risk interception by colony defenses.

### `RESOURCE_ON_GIVEN_FLEET`

- Requests a bundle of minerals, colonists, and/or known secret resources
  delivered on a fleet that is then transferred to the requester.
- The drafting player specifies only the cargo bundle.
- The fulfilling player may use any fleet.

### `FLEET_BY_SHIP_COUNT`

- Requests one or more fleets totaling at least `n` ships.
- Any qualifying fleet transfer to the requesting player counts.
- Fulfilment is matched automatically to the oldest accepted eligible
  contract first.

### `SPECIFIC_FLEET`

- Used only for offered/rewarded fleets.
- The drafting player selects the exact fleet in the wizard.
- The recipient should receive a report-like hyperlink to inspect that
  fleet from the diplomatic request.
- If the fleet is destroyed, scuttled, merged away, or transferred to a
  different owner before completion, the contract immediately expires.
- No hard order lock is applied; the offering player may still reposition
  or misuse the fleet and thereby break the deal.

## Resource Scope

Resources in V1 include:

- ironium
- boranium
- germanium
- colonists
- secret resources

V1 limitation:

- Players may request resources.
- Players do not directly offer resource payouts as the reward side of a
  contract, because those cannot be completed automatically under the
  current rules.

## Secret Resource Visibility

- Players may only offer or request secret resources they already know.
- When shown to a player who does not know the secret resource, display
  it as quantity plus unknown type, for example `25kt ???`.
- This rule applies in:
  - diplomacy screen
  - diplomatic alerts/messages
  - Play CLI
  - email rollups

## Fulfilment Rules

### Matching

- Deliveries and fleet transfers are not manually attached to contracts by
  orders.
- Matching is automatic.
- When multiple accepted contracts could consume the same event, the
  earliest accepted eligible contract is fulfilled first.

### Timing

- Recipient must accept and fulfil within the contract deadline.
- Acceptance may happen on the final valid year.
- If accepted at the edge of expiry, the obligation must be completed by
  orders executed in the immediately following turn window.
- The draft may optionally extend the deadline by `x` years on acceptance.

### Completion Effects

- When a contract completes, any promised reward clause fires
  automatically.
- `TECHNOLOGY` rewards create permanent player technology grants.
- `SPECIFIC_FLEET` rewards auto-transfer the selected fleet immediately on
  completion.
- `STANCE` rewards or penalties post pending stance changes immediately on
  completion.

### Demands and `or else`

In V1, `or else` supports:

- `STANCE`
- `NOTHING`

If a demand is declined or expires unresolved:

- the `or else` clause fires automatically
- if it is a stance clause, it posts to the pending-stance system

## Turn-Lock Restrictions

Players may not send or modify diplomacy after:

- they have turned in, or
- the next turn is due in less than one minute

Blocked actions include:

- send
- accept
- decline
- counter
- revoke

This avoids last-minute changes to capabilities, especially immediate
technology grants.

## Message and Alert Behavior

Contracts require a contract-linked alert layer in addition to normal
`GameMessage` rows.

Behavior:

- incoming contracts create a diplomatic-priority alert
- alerts are inserted into:
  - web message list
  - Play CLI message list
  - email rollup list
- diplomatic-priority alerts use a blue-purple highlight distinct from
  ordinary red priority alerts
- alert stays pinned until handled:
  - `ACCEPTED`
  - `DECLINED`
  - `COUNTERED`
  - `EXPIRED`
  - `REVOKED`

Viewing the diplomacy page alone is not enough to clear the pin.

Accepted but unresolved contracts should remain visible in the diplomacy
detail even after the incoming alert is no longer pinned.

## UI Notes

Recommended entry point:

- a button in the selected race detail panel opening a pop-out wizard

Wizard inputs:

- temperature
- recipient race
- request clause
- reward / consequence clause
- deadline
- deadline extension on acceptance
- optional suggested colony for world-delivery requests

The diplomacy detail panel should also show:

- pending / active contracts with the selected race
- historical handled contracts
- actions for incoming contracts:
  - accept
  - decline
  - counter

## Technology Grant Model

V1 needs a persistent player-owned technology entitlement table.

Rules:

- technology remains granted permanently once received
- granted tech participates in the same lookup layer as normal unlocked
  tech
- grant may make a technology available even if the player's race type
  could not ordinarily research or use it
- ordinary research progression is unchanged

## Non-Goals For V1

- multi-clause contracts
- automatic resource reservation
- order-level contract tagging
- fleet locking while offered
- resource reward clauses
- `or else` effects beyond stance or no-op
- treaty bundles or broader alliance systems
