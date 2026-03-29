# Repository Agent Notes

- `AGENTS.md` is the canonical place for agent workflow instructions in this repo.
- Keep [CLAUDE.md](/Users/bradleygray/src/dj4xol/CLAUDE.md) focused on project guidance, architecture, and coding conventions.
- After completing one or more features or bugfixes, always include a brief commit-message-like summary line in the response so the user can quickly reuse or adapt it for git history.

## Defaults and Tech Tree Sync Procedure (Canonical)

- Until `1.0`, defaults-backed data is expected to change regularly. If `dj4xol/fixtures/defaults.yaml` changes for any of these models, add a sync migration:
  - `ServerRaceType`
  - `ServerRace`
  - `ResearchCategory`
  - `Technology`
  - `ResearchLevelPrerequisite`
- Prefer the reusable helper in `dj4xol/default_sync.py`:
  - `sync_factory_defaults(force=True)`
  - Use this inside a migration `RunPython` wrapper.
- Avoid one-off ad hoc tech/default sync implementations unless there is a schema-safety reason.
- `pyenv exec python manage.py sync_defaults` is the preferred manual refresh command for existing DBs.
- `sync_tech_tree` remains a legacy alias and should not be the preferred name.

## Superseding Older Sync Migrations

- When a newer fixture-sync migration fully supersedes earlier defaults/tech-tree resync migrations:
  - keep old migration nodes for graph/history stability,
  - rewrite older sync bodies to explicit no-op,
  - ensure only the latest canonical defaults sync migration actually loads `defaults.yaml`.
- Rationale:
  - prevents replaying modern fixtures through historical schemas on every fresh install,
  - reduces migration fragility,
  - keeps historical checkouts responsible for their own correct migration behavior at that revision.
