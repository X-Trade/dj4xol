# dj4xol

A Django-based 4X space strategy game inspired by Stars!

## Project Structure

- `dj4xol/` - Main Django app
  - `models.py` - Core models: Account, Game, Player, Star, Ship, ServerRace, ServerRaceType
  - `factory.py` - GameFactory for creating and managing games
  - `turn.py` - Turn generation logic
  - `views.py` - Django views
  - `forms.py` - Django forms for game/race creation, joining, registration
  - `messages.py` - In-game message factories
  - `starmap.py` - Map rendering
  - `objectdetails.py` - Detail panel data

## Model Hierarchy

- Django User → Account (dj4xol account with alias) → Player (per-game instance with race)
- ServerRaceType defines race mechanics/bonuses
- ServerRace is a named race template (public or user-owned) referencing a ServerRaceType
- Player copies race details (name, plural_name, formal_name, race_type) when joining a game

## Coding Principles

- **DRY**: Minimize duplicated code. If two paths do the same thing, they should call the same function.
- **Pythonic**: Clean, readable code following Python best practices.
- **No boilerplate**: Avoid repetition and irrelevant verbosity.
- **Sensible defaults**: Models and test fixtures should have sensible defaults so you don't spell out every field.
- **Single responsibility**: One function, one job. Compose small functions rather than large monolithic ones.

### `_rules` Pattern (Important)

- Put core game arithmetic/probability logic in small pure-Python `*_rules.py` modules.
- Keep `models.py`, `views.py`, `turn.py`, and frontend-adjacent Python code (for example Brython) as thin callers of these shared rules.
- Primary goal: share identical gameplay logic between backend and frontend so UI previews and server outcomes match.
- Secondary benefit: migrations and scripts can reuse the same rules, reducing drift between historical/data-update paths and live runtime behavior.
- This also makes rules easy to unit test without ORM/database setup.
- If model field defaults or older migrations reference model-level helper functions, keep lightweight compatibility wrappers in `models.py` that delegate to the shared rules module.

## Technology Stack

- **Python-first**: Do everything possible in Django without additional tools/frameworks. Pure Python.
- **Future frontend**: Investigate Python on the frontend (Brython or PyScript) for browser-side interactivity.

## Development Environment

- Uses **pyenv-virtualenv** for Python version and virtual environment management
- Preferred command pattern: `pyenv exec python ...` (for example: `pyenv exec python manage.py test`)
- Project env name is `dj4xol`; one-shot alternative: `PYENV_VERSION=dj4xol python ...`
- If `python` is not on PATH in a shell session, still use `pyenv exec python ...`
- Do not try to source `.venv/bin/activate` or similar

## Docs Workflow

- Use `doc/` for focused implementation notes, cleanup rationales, migration writeups, and other task-specific design docs.
- Add actionable follow-up items to `todo.txt` when a doc introduces concrete cleanup or feature work.
- `doc/plan.txt` is mainly reserved for broader future gameplay-device ideas and exploratory design notes, not general implementation cleanup tracking.

## Technology Sync Policy

- Until version `1.0`, expect regular technology-tree churn. When fixture-backed research categories, technologies, or research prerequisites change in `dj4xol/fixtures/defaults.yaml`, also add a technology synchronization migration so `migrate` brings existing databases forward.
- Prefer the existing reusable sync helper in `dj4xol/default_sync.py`: `sync_factory_defaults(force=True)`, wrapped in a migration `RunPython` function, rather than copying another one-off fixture sync implementation unless there is a migration-safety reason to do otherwise.

## Research Stage Bands

- `L0-L3`: early hardcore grind for a challenging start
- `L0-L6`: early game
- `L7-L12`: mid-game
- `L13-L18`: late-game
- `L19-L26`: end-game

## Game Rules

- Games can exist with zero players (allows cleanup/admin scenarios)
- Turn generation requires at least one player
- Planets with zero population lose ownership
- Joining auto-closes after `join_until_year` if set
