from __future__ import unicode_literals

import json

from django.db import migrations, models


def _safe_params(tech):
    try:
        data = json.loads(getattr(tech, 'params_json', '') or '{}')
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _unique_hull_name(HullDesign, base_name, technology):
    base_name = (base_name or 'Hull').strip() or 'Hull'
    base_name = base_name[:64]
    if not HullDesign.objects.filter(name=base_name).exists():
        return base_name

    suffix = getattr(technology, 'short_id', '') or 'hull'
    suffix = str(suffix).strip()[:12] or 'hull'
    trimmed = base_name[: max(1, 64 - len(suffix) - 3)].rstrip()
    candidate = '%s [%s]' % (trimmed, suffix)
    if not HullDesign.objects.filter(name=candidate).exists():
        return candidate

    idx = 2
    while True:
        extra = ' %s' % idx
        trimmed = base_name[: max(1, 64 - len(extra))].rstrip()
        candidate = '%s%s' % (trimmed, extra)
        if not HullDesign.objects.filter(name=candidate).exists():
            return candidate
        idx += 1


def link_hull_designs(apps, schema_editor):
    Technology = apps.get_model('dj4xol', 'Technology')
    HullDesign = apps.get_model('dj4xol', 'HullDesign')

    for technology in Technology.objects.filter(tech_type='HULL').order_by('id'):
        if HullDesign.objects.filter(technology_id=technology.id).exists():
            continue

        existing = HullDesign.objects.filter(
            technology__isnull=True,
            name=technology.name,
        ).order_by('id').first()
        if existing is not None:
            existing.technology_id = technology.id
            existing.save(update_fields=['technology'])
            continue

        params = _safe_params(technology)
        hull = HullDesign(
            technology_id=technology.id,
            name=_unique_hull_name(HullDesign, technology.name, technology),
            thumbnail_class=(
                str(params.get('hull_thumbnail_class') or '').strip().lower()
                or 'scout'
            ),
            offense_offset=float(params.get('offense_level', 0.0) or 0.0),
            defense_offset=float(params.get('defense_level', 0.0) or 0.0),
            cargo_capacity=int(params.get('max_cargo_capacity', 0) or 0),
            fuel_capacity=int(params.get('max_fuel', 100) or 100),
            enabled=bool(getattr(technology, 'enabled', True)),
        )
        hull.save()


def unlink_hull_designs(apps, schema_editor):
    HullDesign = apps.get_model('dj4xol', 'HullDesign')
    HullDesign.objects.update(technology=None)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0177_sync_supermax_fuel_factory_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='hulldesign',
            name='technology',
            field=models.OneToOneField(
                blank=True,
                limit_choices_to={'tech_type': 'HULL'},
                null=True,
                on_delete=models.CASCADE,
                related_name='hull_design',
                to='dj4xol.Technology',
            ),
        ),
        migrations.RunPython(link_hull_designs, unlink_hull_designs),
    ]
