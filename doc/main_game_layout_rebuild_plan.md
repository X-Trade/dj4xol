## Main Game Layout Rebuild Plan

This is the safer responsive pattern to return to after the current
main game view rollback.

### Goals

- 1-column scrolling mobile/touch layout:
  - Starmap first
  - Detail and Orders next
  - Messages last
- 2-column desktop/tablet layout:
  - Starmap and Messages in column 1
  - Detail and Orders stacked in column 2
- 3-column desktop layout:
  - Starmap and Messages in column 1
  - Detail in column 2
  - Orders in column 3
- Desktop panel collapse/minimise must preserve usable vertical space
- Detail and Orders should split column 2 as `60/40` when both are open
- If one panel is collapsed, the other fills the remaining space
- Collapsed headers should stay stacked from the top downward
- Behaviour must be reliable in Chrome, Safari, Firefox, and iPhone/iPad

### Core Approach

- Keep one stable DOM structure across all breakpoints
- Do not use `display: contents` for core layout
- Do not reparent panels in JavaScript on resize
- Do not rely on `:has()` for essential layout behaviour
- Use simple state classes such as `.is-collapsed` for panel behaviour

### Proposed Structure

```html
<div class="game-layout">
  <section class="map-slot">...</section>

  <div class="right-stack">
    <section class="detail-slot">...</section>
    <section class="orders-slot">...</section>
  </div>

  <section class="messages-slot">...</section>
</div>
```

### Mobile Layout

- Use a plain vertical flex layout
- Visual order remains:
  - Starmap
  - Right stack
  - Messages
- Let the page scroll naturally
- Keep panel content scrollable internally only where really needed

### Two-Column Layout

- Use an outer 2-column, 2-row grid
- Column 1:
  - Starmap in row 1
  - Messages in row 2
- Column 2:
  - `right-stack` spans both rows
- Inside `right-stack`:
  - use vertical flex
  - `detail-slot` gets `flex: 6`
  - `orders-slot` gets `flex: 4`

### Three-Column Layout

- Outer layout still keeps Starmap and Messages in column 1
- `right-stack` spans columns 2 and 3
- Inside `right-stack`:
  - switch to a 2-column grid
  - Detail stays in column 1
  - Orders stays in column 2
- If there is no Orders panel:
  - Detail stays in column 1 only
  - Column 3 remains empty/reserved

### Collapse Behaviour

- Collapse state should be driven by explicit classes
- In 2-column mode:
  - both open: `60/40`
  - detail collapsed: orders fills remaining height
  - orders collapsed: detail fills remaining height
  - both collapsed: both shrink to header height
- In 3-column mode:
  - each panel stays in its own column
  - collapsing only reduces that panel to header height
- Collapsed headers should remain top-aligned with normal spacing

### Cross-Browser Rules

- Avoid `display: contents`
- Avoid DOM movement on breakpoint changes
- Avoid making Safari interpret nested grid/flex mode switches differently
- Keep footer and non-panel UI outside the main layout grid

### Rebuild Strategy

1. Restore a stable baseline first
2. Rebuild the main game layout with the fixed wrapper structure above
3. Re-test after each layout step in:
   - Chrome desktop
   - Safari desktop
   - iPhone Safari
   - Firefox desktop
4. Only reintroduce one layout feature at a time

