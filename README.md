# dj4xol

Duh-Jacks-Ohl (`dj4xol`) is a turn-based 4X space strategy game built as a
Django application, inspired by classic PBEM-style empire games.

Players expand from a homeworld, manage colonies and minerals, commission
fleets, research technology, and resolve movement, combat, and invasion during
turn generation.

## Current State

The project is actively developed and playable in MVP form.

Implemented systems include:
- Multi-game server with account registration, profile onboarding, invites, email updates, and spectator mode
- Responsive web UI with Classic, LCARS, and Win95 themes, plus public landing/gallery pages
- Optional advanced player CLI interface in the terminal and web game view
- Race creation with balance-point budgeting and habitability tuning
- Starmap planning with fleet movement, intercept, transfer, merge, colonise, scuttle, and turn reports
- Colony economy with population, mines, factories, labs, defences, shipyards, and terraforming
- Research categories, allocations, prerequisites, unlocks, and technology directory/help
- Space combat, invasions, fleet fuel, scanners, and other core turn-resolution systems
- Recent MVP extensions including anomalies, secret resources, remote mining, bombardment, wormholes, and game-speed setup options

## Current Priorities

Near-term work is tracked in `todo.txt`. Current focus includes:
- Gameplay and tech tree progression balancing
- Diplomacy
- Ship design (basic, then advanced)
- Trade contracts/negotiation
- Mine fields
- Fuel factories and fleet-to-fleet refuelling
- Instant merge/split fleet interaction screen
- Custom server help pages (wiki/CMS style)
- Ongoing Brython refactor/expansion for UI logic

## Future Possibilities

Longer-term design ideas live in `doc/plan.txt` and are intentionally exploratory.
Examples include:
- Stability systems, unrest, and breakaway colonies
- Megaproject infrastructure such as citadels, stargates, micromanagers, and superweapons
- Garrisons and other colony structures that trade economy for stability or defence
- More extreme anomaly and galaxy events, including disappearing worlds and new-star creation
- Data-driven ship components, hulls, and tech publishing workflows
- Experimental setup/admin tooling and balance controls
- Pluggable AI player types and LLM-assisted opponents or tooling

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
