## Docker Prod-Like Environment Plan

This project should have a Docker setup that is useful for reproducing
production deployment behaviour locally, especially for:

- `gunicorn` application serving
- `nginx` reverse proxy and static file serving
- `collectstatic` output and hashed asset behaviour
- environment variable driven configuration
- clearer separation between source static files and runtime-generated files

### Goals

- Keep all Docker configuration under `docker/`
- Make the local Docker stack closer to production than the current
  single-container `runserver` setup
- Preserve a simple day-to-day local Python workflow outside Docker
- Allow Safari/iPhone testing against a locally served prod-like stack
- Avoid treating generated `staticfiles/` as source-controlled artefacts

### Proposed Services

#### `app`

- Builds the Django project image
- Installs runtime dependencies plus `gunicorn`
- Runs:
  - `migrate`
  - `collectstatic`
  - `gunicorn testsite.wsgi:application`
- Mounts:
  - repository source for development
  - shared static volume for collected assets
  - shared media volume for future uploads/media

#### `nginx`

- Proxies dynamic requests to `app`
- Serves `/static/` directly from the shared static volume
- Serves `/media/` from a shared media volume

### Files To Add

- `docker/app/Dockerfile`
- `docker/app/entrypoint.sh`
- `docker/nginx/nginx.conf`
- `docker/compose.yml`
- `docker/compose.debug.yml`

### Files To Remove Or Replace

- root `Dockerfile`
- root `docker-compose.yml`
- root `docker-compose.debug.yml`

### Runtime Notes

- Docker is not required for normal local development
- Intended usage should be:

```bash
docker compose -f docker/compose.yml up --build
```

- Debug variant should stay opt-in

### Static And Media

- `collectstatic` output should go to a dedicated runtime volume
- Docker should not rely on rsyncing generated `staticfiles/`
- Long term, user-managed gallery or upload-like content should move out
  of source static paths and into a proper media path/volume

### Limitations

- This will improve production-parity testing
- It will not by itself reproduce Safari browser bugs; Safari still needs
  to be used against the local Docker-served app

