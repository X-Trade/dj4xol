import hashlib

from django.db import migrations


def _stable_seed_value(seed):
    text = str(seed or '').encode('utf-8')
    return int(hashlib.md5(text).hexdigest()[:8], 16)


def _pick_level(seed, options):
    if not options:
        return 'NONE'
    return options[_stable_seed_value(seed) % len(options)]


def backfill_salvage_danger_levels(apps, schema_editor):
    Salvage = apps.get_model('dj4xol', 'Salvage')
    for salvage in Salvage.objects.all():
        if getattr(salvage, 'danger_level', ''):
            continue
        salvage_type = str(getattr(salvage, 'salvage_type', '') or '').upper()
        seed = 'salvage:%s:%s' % (
            getattr(salvage, 'short_id', None) or getattr(salvage, 'id', None) or '',
            getattr(salvage, 'name', '') or '',
        )
        if salvage_type == 'ANCIENT_DEBRIS':
            level = _pick_level(seed, ['MEDIUM', 'HIGH'])
        elif salvage_type == 'ASTEROID_FIELD':
            level = _pick_level(seed, ['LOW', 'MEDIUM'])
        else:
            # Existing raw salvage cannot be distinguished between combat debris and dumped cargo,
            # so prefer the safer legacy-compatible value.
            level = 'NONE'
        salvage.danger_level = level
        salvage.save(update_fields=['danger_level'])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0154_salvage_danger_level'),
    ]

    operations = [
        migrations.RunPython(backfill_salvage_danger_levels, migrations.RunPython.noop),
    ]
