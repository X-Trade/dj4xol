# dj4xol Agent Guide

`AGENTS.md` is the canonical place for both agent workflow instructions and project guidance in this repo.

## Response Workflow

- After completing one or more features or bugfixes, always include a brief commit-message-like summary line in the response so it can be reused or adapted for git history.

## Project Structure

- `dj4xol/` - Main Django app
  - `models.py` - Core models: `Account`, `Game`, `Player`, `Star`, `Ship`, `ServerRace`, `ServerRaceType`
  - `factory.py` - `GameFactory` for creating and managing games
  - `turn.py` - Turn generation logic
  - `views.py` - Django views
  - `forms.py` - Django forms for game/race creation, joining, registration
  - `messages.py` - In-game message factories
  - `starmap.py` - Map rendering
  - `objectdetails.py` - Detail panel data

## Model Hierarchy

- Django `User` -> `Account` -> `Player` (per-game instance with race)
- `ServerRaceType` defines race mechanics/bonuses
- `ServerRace` is a named race template (public or user-owned) referencing a `ServerRaceType`
- `Player` copies race details (`name`, `plural_name`, `formal_name`, `race_type`) when joining a game

## Coding Principles

- **DRY**: If two paths do the same thing, call the same function.
- **Pythonic**: Keep code clean and readable.
- **No boilerplate**: Avoid repetitive low-value code.
- **Sensible defaults**: Models and fixtures should reduce required boilerplate.
- **Single responsibility**: Prefer small composable functions.
- **Modifier display semantics**:
  - If value already includes modifier, show in brackets (for example `120BP/Year (+20%)` or `12(+10)`).
  - If modifier is shown separately and applied afterward, show without brackets (for example `30% -50%`).

## `_rules` Pattern (Important)

- Put core game arithmetic/probability logic in pure-Python `*_rules.py` modules.
- Keep `models.py`, `views.py`, `turn.py`, and frontend-adjacent Python thin callers of shared rules.
- Goals:
  - backend/frontend logic parity,
  - reduced drift between live runtime and migrations/scripts,
  - easier unit testing without ORM setup.
- If historical model defaults/migrations depend on model helpers, keep lightweight compatibility wrappers in `models.py` delegating to rules modules.

## Technology Stack

- **Python-first**: Prefer pure Django/Python solutions.
- **Future frontend**: Brython/PyScript may be used for browser-side interactivity.

## Development Environment

- Uses **pyenv-virtualenv**
- Preferred command pattern: `pyenv exec python ...` (for example `pyenv exec python manage.py test`)
- Env name: `dj4xol` (one-shot alternative: `PYENV_VERSION=dj4xol python ...`)
- If `python` is not on PATH, still use `pyenv exec python ...`
- Do not source `.venv/bin/activate`-style paths

## Docs Workflow

- Use `doc/` for implementation notes, cleanup rationales, migration writeups, and task-specific design docs.
- Add concrete follow-up actions to `todo.txt` when docs introduce actionable work.
- `doc/plan.txt` is for broader future gameplay/device ideas and exploratory notes, not general cleanup tracking.

## Defaults and Tech Tree Sync Procedure (Canonical)

- Until `1.0`, expect regular fixture-backed defaults churn.
- If `dj4xol/fixtures/defaults.yaml` changes for defaults-backed:
  - `ServerRaceType`
  - `ServerRace`
  - `ResearchCategory`
  - `Technology`
  - `ResearchLevelPrerequisite`
  also add a synchronization migration so `migrate` updates existing DBs.
- Prefer the reusable helper in `dj4xol/default_sync.py`:
  - `sync_factory_defaults(force=True)`
  - wrapped in migration `RunPython`.
- Avoid one-off ad hoc sync implementations unless there is a migration-safety reason.
- Preferred manual refresh command: `pyenv exec python manage.py sync_defaults`.
- `sync_tech_tree` remains a legacy alias and should not be preferred.

## Superseding Older Sync Migrations

- When a newer fixture-sync migration fully supersedes older defaults/tech-tree resync migrations:
  - keep old migration nodes for graph stability,
  - rewrite older resync bodies to explicit no-op,
  - ensure only the latest canonical defaults sync migration loads `defaults.yaml`.
- Rationale:
  - avoids replaying modern fixtures through historical schemas on fresh installs,
  - reduces migration fragility,
  - preserves historical checkout behavior for its revision.

## Research Stage Bands

- `L0-L3`: early hardcore grind
- `L0-L6`: early game
- `L7-L12`: mid-game
- `L13-L18`: late-game
- `L19-L26`: end-game

## Game Rules

- Games can exist with zero players (cleanup/admin scenarios)
- Turn generation requires at least one player
- Planets with zero population lose ownership
- Joining auto-closes after `join_until_year` if set
