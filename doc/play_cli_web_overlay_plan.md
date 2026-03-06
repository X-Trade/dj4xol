# Play CLI Web Overlay Plan

## Goal

Expose the existing Play CLI inside the main game web view through a terminal
overlay, without opening a generic remote command surface that can be abused.

The desired UX is:

- on the main game screen, pressing `/` opens a terminal overlay
- the overlay appears over the game UI, anchored at the bottom of the screen
- output scrolls upward like a traditional terminal
- the opening slash is inserted automatically
- on first open, the player sees the normal connection/help banner
- `/exit` closes the overlay
- typing in the overlay must not also type into underlying page controls
- pressing `/` while focused in a text field, textarea, select, or editable UI
  must do nothing

## Why This Needs A Web API

The current Play CLI is implemented as a Django management command in
`dj4xol/management/commands/play.py`. That works for a local terminal, but not
for browser interaction.

The browser should not shell out to a management command.

Instead, both the terminal command and the web overlay should call the same
shared Python command runner, with separate transport layers:

- management command transport for local terminal use
- authenticated HTTP transport for browser use

This avoids logic drift and keeps browser access inside the normal web auth and
CSRF model.

## Recommended Architecture

Extract the command execution logic into a shared service, for example:

- `dj4xol/play_cli.py`

That service should:

- resolve the current `game` and `player`
- accept a single command line
- return structured output lines
- return command metadata such as `close_overlay` for `/exit`
- avoid any direct terminal I/O

Then:

- `dj4xol/management/commands/play.py` becomes a thin wrapper around the shared
  service
- a new authenticated web view exposes the same service over JSON

## Proposed Web Endpoints

### `GET /<game_short_id>/play/bootstrap/`

Returns the initial transcript for the overlay:

- connected banner
- priority messages
- `Type /help for available commands.`

This should use the same shared service output as terminal startup, so the
browser and terminal behave the same.

### `POST /<game_short_id>/play/command/`

Request body:

```json
{
  "command": "/stars"
}
```

Response body:

```json
{
  "ok": true,
  "lines": [
    "abcd1234:",
    "  name: Homeworld"
  ],
  "close_overlay": false
}
```

For `/exit`, return:

```json
{
  "ok": true,
  "lines": ["Disconnected."],
  "close_overlay": true
}
```

## Security Requirements

This is the part that matters most.

### Authentication

Use normal Django session authentication only.

- no anonymous access
- no tokenless public endpoint
- no separate CLI password flow in the browser

The server must resolve the player from the authenticated account in the same
way as the normal game view.

### Authorization

Re-use the same player/game access checks as the main game page.

The endpoint must reject:

- users without a `dj4xol_account`
- accounts not in the game
- defeated players if the CLI would already refuse them
- spectators, unless spectator CLI support is explicitly designed later

### CSRF

All command execution requests must be same-origin `POST` with CSRF protection.

That prevents a third-party site from driving player actions through the
browser session.

### No Shell Execution

The web endpoint must never invoke a subprocess, shell command, or management
command.

Only the internal Play CLI command parser is allowed.

### Command Surface

Do not accept arbitrary Python or admin actions.

The only valid inputs are the same supported Play CLI commands already handled
by the shared command runner.

### Input Limits

Add strict server-side limits:

- maximum command length, for example `256`
- single-line input only
- reject empty or whitespace-only requests
- reject commands containing embedded newlines or null bytes

### Rate Limiting

This endpoint will be easy to spam accidentally or intentionally.

Add lightweight per-account throttling, for example:

- burst limit per player per game
- short cooldown after repeated failures

If application-level throttling is not already present, a simple cache-backed
rate limiter for this endpoint is sufficient for phase one.

### Auditability

Mutating commands should be logged with:

- account id
- player id
- game id
- command
- timestamp
- success/failure

That is useful for abuse review and debugging.

## Frontend Overlay Design

The overlay should live in `dj4xol/templates/dj4xol/main.html` and a dedicated
static JS/CSS file pair, rather than embedded ad hoc script.

Suggested assets:

- `dj4xol/static/dj4xol/js/play_terminal.js`
- `dj4xol/static/dj4xol/css/play_terminal.css`

### Overlay Structure

- full-width bottom overlay
- black or near-black translucent background
- monospace text
- scrollback region above the prompt
- single command input row at the bottom

The input should be the only focused element while the overlay is open.

### Opening Behavior

Attach a `keydown` listener on the document in capture phase.

Open the overlay only when all of these are true:

- key is `/`
- no `ctrl`, `meta`, or `alt` modifier
- overlay is not already open
- event target is not an editable control
- turn lock does not disable interaction entirely, unless read-only CLI use is
  explicitly allowed after turn-in

Editable targets that must block opening:

- `input`
- `textarea`
- `select`
- any element with `contenteditable`
- any element inside the rename popover
- any order form text or numeric input

When opening:

- call `preventDefault()` and `stopPropagation()`
- show the overlay
- focus the terminal input
- set the input value to `/`
- if this is the first open in the page session, call bootstrap and append the
  welcome transcript first

### Input Isolation

When the overlay is open:

- all terminal key handling should stop propagation
- the underlying page should not receive command keystrokes
- `Escape` may close the overlay as an additional convenience, but `/exit`
  remains the canonical command

### Closing Behavior

The overlay closes when:

- the user submits `/exit`
- optionally the user presses `Escape`

Closing should:

- blur the terminal input
- hide the overlay
- clear the active prompt state
- not submit anything to underlying page elements

## Shared Command Runner Behavior

The shared runner should return structured output instead of writing directly to
`stdout`.

For example:

```python
{
    "lines": ["Connected: game=...", "Type /help for available commands."],
    "close_overlay": False,
}
```

That makes it usable from:

- terminal wrapper
- browser JSON endpoint
- tests

It also gives one place to enforce:

- command validation
- command length limits
- output formatting
- `/exit` handling

## Suggested Rollout

### Phase 1

Read-only browser CLI:

- `/help`
- `/status`
- `/reports`
- `/stars`
- `/fleets`
- `/colonies`
- `/anomalies`
- `/salvage`
- `/messages`
- `/detail`

This is the safest initial transport rollout.

### Phase 2

Add mutating commands once the endpoint and audit/rate-limit behavior are
proven:

- `/research`
- `/orders ... clear`
- `/orders ... add ...`
- `/done`

Mutating commands should only be enabled once CSRF, throttling, and logging are
in place.

## Testing Requirements

### Backend

- authenticated player can bootstrap and execute commands
- non-player cannot access endpoint
- cross-game access is rejected
- CSRF-protected command execution works
- `/exit` returns `close_overlay=true`
- invalid commands return safe error output
- command length and newline rejection are enforced
- throttling behavior is covered

### Frontend

- pressing `/` on main page opens overlay
- pressing `/` inside `#rename-input` does not open overlay
- pressing `/` inside order form inputs does not open overlay
- terminal input captures keystrokes without leaking to underlying controls
- first open shows welcome/help transcript
- `/exit` closes overlay
- overlay output scrolls correctly

## Open Questions

- Should the browser overlay be available after a player has already turned in,
  for read-only commands only?
- Should spectators eventually get a reduced terminal overlay, or should this be
  player-only permanently?
- Do we want command history in browser memory for the current page session?

## Recommendation

Proceed with this in two implementation steps:

1. extract a shared Play CLI command runner and add authenticated JSON
   bootstrap/command endpoints
2. add the in-page terminal overlay on `main.html`, initially with read-only
   commands enabled

That gives a secure foundation first, and avoids coupling UI work to terminal
parsing internals.
