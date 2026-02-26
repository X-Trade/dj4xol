# dj4xol

Duh-Jacks-Ohl (`dj4xol`) is a turn-based 4X space strategy game built as a
Django application, inspired by classic PBEM-style empire games.

Players expand from a homeworld, manage colonies and minerals, commission
fleets, research technology, and resolve movement, combat, and invasion during
turn generation.

## Current State

The project is actively developed and playable in MVP form.

Implemented systems include:
- Multi-game server with account registration, profile onboarding, and invites
- Race creation with balance-point budgeting and habitability tuning
- Starmap with fleet movement, intercept, transfer, merge, colonise, and scuttle
- Colony economy (population, mines, factories, labs, defences, shipyards)
- Research categories, allocations, unlocks, and technology directory/help
- Fleet commissioning with tech-derived offence/defence and hull capacities
- Space combat and invasions resolved during turn generation
- Message log/history and report-style visibility

## Current Priorities

Near-term work is tracked in `todo.txt`. Current focus includes:
- Colony Micromanager (as unlockable automation)
- Fleet-to-fleet refuelling
- Ship design (basic, then advanced)
- Instant merge/split fleet interaction screen
- Custom server help pages (wiki/CMS style)
- Sensor/radar visibility rules and fog-of-war style information control
- Preventing unsporting information leaks between players
- Diplomacy
- Trade contracts/negotiation
- Ongoing Brython refactor/expansion for UI logic

## Future Possibilities

Longer-term design ideas live in `plan.txt` and are intentionally exploratory.
Examples include stability systems and megaprojects, anomalies, expanded tech
and ship design tooling, alternate galaxy generation modes, and pluggable AI.
These are ideas, not commitments.

## Tech Stack

- Python + Django (`1.11.x`)
- SQLite by default for local development
- Brython for selected browser-side logic
- Pillow for image processing scripts/assets

## Development Environment

This project uses `pyenv` + `pyenv-virtualenv`.

Preferred command style:
- `pyenv exec python ...`

Example:
- `pyenv exec python manage.py test`

## Quick Start (Local)

1. Clone the repository.
2. Install dependencies:
```bash
pyenv exec pip install -r requirements-dev.txt
```
3. Run migrations:
```bash
pyenv exec python manage.py migrate
```
4. Start the dev server:
```bash
pyenv exec python manage.py runserver
```
5. Open:
- `http://localhost:8000/` (redirects to `/4x/`)
- `http://localhost:8000/4x/`

## Running Tests

Run the full test suite:
```bash
pyenv exec python manage.py test
```

Run a specific module/class:
```bash
pyenv exec python manage.py test dj4xol.tests.resource_generation
```

## Versioning

Application version is declared once in:
- `dj4xol/version.py` (`APP_VERSION`)

This value is reused by:
- Python package exports (`dj4xol.__version__`)
- `setup.py` package metadata
- Template context (`app_version`)
- Frontend JS (`window.DJ4XOL_VERSION`)

## Project Layout

- `dj4xol/models.py` - Core data model (games, players, stars, fleets, research)
- `dj4xol/factory.py` - Game creation/join flow and starting state assignment
- `dj4xol/turn.py` - Turn generation and order execution
- `dj4xol/research.py` - Research budgeting/allocation/progression
- `dj4xol/objectdetails.py` - Detail panel data shaping
- `dj4xol/messages.py` - In-game message generation
- `dj4xol/templates/dj4xol/` - UI templates
- `dj4xol/static/dj4xol/` - CSS/JS/Brython/static assets

## Shared Rules Pattern

Gameplay arithmetic should live in pure-Python `*_rules.py` modules where
possible. Server code and frontend-adjacent Python can then call the same
logic, which keeps behaviour consistent across UI previews and turn resolution.

## License

See `LICENSE`.
