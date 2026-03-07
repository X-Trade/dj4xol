#!/bin/bash
set -e
pyenv exec python -m dj4xol.catalog_all_thumbs
pyenv exec python manage.py test dj4xol.tests.thumbnails dj4xol.tests.views
