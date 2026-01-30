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

## Technology Stack

- **Python-first**: Do everything possible in Django without additional tools/frameworks. Pure Python.
- **Future frontend**: Investigate Python on the frontend (Brython or PyScript) for browser-side interactivity.

## Game Rules

- Games can exist with zero players (allows cleanup/admin scenarios)
- Turn generation requires at least one player
- Planets with zero population lose ownership
- Joining auto-closes after `join_until_year` if set
