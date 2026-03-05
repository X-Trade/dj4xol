from pathlib import Path
from django.db import migrations, models


LEGACY_STAR_THUMBNAILS = [
    "dj4xol/images/thumbs/star/all/1__r01_c01.png",
    "dj4xol/images/thumbs/star/all/1__r01_c02.png",
    "dj4xol/images/thumbs/star/all/1__r01_c03.png",
    "dj4xol/images/thumbs/star/all/1__r02_c01.png",
    "dj4xol/images/thumbs/star/all/1__r02_c02.png",
    "dj4xol/images/thumbs/star/all/1__r02_c03.png",
    "dj4xol/images/thumbs/star/all/2__r01_c01.png",
    "dj4xol/images/thumbs/star/all/2__r01_c02.png",
    "dj4xol/images/thumbs/star/all/2__r01_c03.png",
    "dj4xol/images/thumbs/star/all/2__r02_c01.png",
    "dj4xol/images/thumbs/star/all/2__r02_c02.png",
    "dj4xol/images/thumbs/star/all/2__r02_c03.png",
    "dj4xol/images/thumbs/star/all/3__r01_c01.png",
    "dj4xol/images/thumbs/star/all/3__r01_c02.png",
    "dj4xol/images/thumbs/star/all/3__r01_c03.png",
    "dj4xol/images/thumbs/star/all/3__r02_c01.png",
    "dj4xol/images/thumbs/star/all/3__r02_c02.png",
    "dj4xol/images/thumbs/star/all/3__r02_c03.png",
    "dj4xol/images/thumbs/star/all/3x__r01_c01.png",
    "dj4xol/images/thumbs/star/all/3x__r01_c02.png",
    "dj4xol/images/thumbs/star/all/3x__r01_c03.png",
    "dj4xol/images/thumbs/star/all/3x__r01_c04.png",
    "dj4xol/images/thumbs/star/all/3x__r02_c01.png",
    "dj4xol/images/thumbs/star/all/3x__r02_c02.png",
    "dj4xol/images/thumbs/star/all/3x__r02_c03.png",
    "dj4xol/images/thumbs/star/all/3x__r02_c04.png",
    "dj4xol/images/thumbs/star/all/3x__r03_c01.png",
    "dj4xol/images/thumbs/star/all/3x__r03_c02.png",
    "dj4xol/images/thumbs/star/all/3x__r03_c03.png",
    "dj4xol/images/thumbs/star/all/3x__r03_c04.png",
    "dj4xol/images/thumbs/star/all/4__r01_c01.png",
    "dj4xol/images/thumbs/star/all/4__r01_c02.png",
    "dj4xol/images/thumbs/star/all/4__r01_c03.png",
    "dj4xol/images/thumbs/star/all/4__r02_c01.png",
    "dj4xol/images/thumbs/star/all/4__r02_c02.png",
    "dj4xol/images/thumbs/star/all/4__r02_c03.png",
    "dj4xol/images/thumbs/star/all/5__r01_c01.png",
    "dj4xol/images/thumbs/star/all/5__r01_c02.png",
    "dj4xol/images/thumbs/star/all/5__r01_c03.png",
    "dj4xol/images/thumbs/star/all/5__r02_c01.png",
    "dj4xol/images/thumbs/star/all/5__r02_c02.png",
    "dj4xol/images/thumbs/star/all/5__r02_c03.png",
]


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


def assign_star_thumbnails(apps, schema_editor):
    Star = apps.get_model('dj4xol', 'Star')
    try:
        from dj4xol.star_thumbnail_catalog import ALL_STAR_THUMBNAILS
    except Exception:
        ALL_STAR_THUMBNAILS = []

    legacy_paths = _filter_existing(LEGACY_STAR_THUMBNAILS)
    current_paths = _filter_existing(ALL_STAR_THUMBNAILS)

    for star in Star.objects.filter(thumbnail_path=''):
        seed = star.id or star.short_id or star.name
        chosen = _choose_from_list(seed, legacy_paths)
        if not chosen:
            chosen = _choose_from_list(seed, current_paths)
        if chosen:
            Star.objects.filter(id=star.id).update(thumbnail_path=chosen)


class Migration(migrations.Migration):
    dependencies = [
        ('dj4xol', '0114_add_anomaly_thumbnail_path'),
    ]

    operations = [
        migrations.AddField(
            model_name='star',
            name='thumbnail_path',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.RunPython(assign_star_thumbnails, migrations.RunPython.noop),
    ]
