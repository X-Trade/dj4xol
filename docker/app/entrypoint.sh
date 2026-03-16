#!/bin/sh
set -eu

cd /srv/dj4xol

mkdir -p /srv/dj4xol/data
mkdir -p /srv/dj4xol/staticfiles
mkdir -p /srv/dj4xol/media

python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear

exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    testsite.wsgi:application
