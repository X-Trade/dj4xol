# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from pathlib import Path

from django.db import migrations


CITY_THUMBNAIL_MARKER = '/star/city/'
ALL_STAR_THUMBNAIL_MARKER = '/star/all/'
# One-off backfill should match the current megacity threshold.
CITY_THUMB_POPULATION_THRESHOLD = 9_000_000_000
DEFAULT_STAR_THUMBNAIL = 'dj4xol/images/thumbs/star/all/1__r01_c01.png'


def _seed_to_index(seed, count):
    if count <= 0:
        return 0
    if seed is None:
        return 0
    text = str(seed)
    if not text:
        return 0
    total = 0
    for char in text:
        total = ((total * 131) + ord(char)) & 0xFFFFFFFF
    return total % count


def _choose_from_list(seed, paths):
    if not paths:
        return ''
    idx = _seed_to_index(seed, len(paths))
    return paths[idx]


def _static_root():
    return Path(__file__).resolve().parents[2] / 'dj4xol' / 'static'


def _filter_existing(paths):
    root = _static_root()
    existing = [p for p in paths if (root / p).exists()]
    return existing if existing else list(paths)


def _all_star_thumbnail_paths():
    try:
        from dj4xol.star_thumbnail_catalog import ALL_STAR_THUMBNAILS
    except Exception:
        ALL_STAR_THUMBNAILS = []
    return _filter_existing([
        path for path in ALL_STAR_THUMBNAILS
        if ALL_STAR_THUMBNAIL_MARKER in str(path)
    ])


def restore_city_thumbnails_below_threshold(apps, schema_editor):
    Star = apps.get_model('dj4xol', 'Star')
    all_thumb_paths = _all_star_thumbnail_paths()

    queryset = Star.objects.filter(
        thumbnail_path__contains=CITY_THUMBNAIL_MARKER
    ).only('id', 'short_id', 'name', 'colonists', 'thumbnail_path')

    for star in queryset.iterator():
        try:
            colonists = int(getattr(star, 'colonists', 0) or 0)
        except (TypeError, ValueError):
            colonists = 0

        if colonists > CITY_THUMB_POPULATION_THRESHOLD:
            continue

        seed = star.id or star.short_id or star.name
        replacement = _choose_from_list(seed, all_thumb_paths) or DEFAULT_STAR_THUMBNAIL
        if not replacement or CITY_THUMBNAIL_MARKER in str(replacement):
            continue
        if replacement == star.thumbnail_path:
            continue

        Star.objects.filter(id=star.id).update(thumbnail_path=replacement)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0198_add_ai_player_fields'),
    ]

    operations = [
        migrations.RunPython(
            restore_city_thumbnails_below_threshold,
            migrations.RunPython.noop,
        ),
    ]
