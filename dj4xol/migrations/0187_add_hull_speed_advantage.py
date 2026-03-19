import json

from django.db import migrations, models


def _backfill_hull_speed_advantage(apps, schema_editor):
    HullDesign = apps.get_model('dj4xol', 'HullDesign')

    for hull in HullDesign.objects.select_related('technology').all():
        technology = getattr(hull, 'technology', None)
        if technology is None:
            continue
        try:
            params = json.loads(getattr(technology, 'params_json', '') or '{}')
        except (TypeError, ValueError):
            params = {}
        if not isinstance(params, dict):
            params = {}
        try:
            speed_advantage = float(params.get('warp_advantage', 0.0) or 0.0)
        except (TypeError, ValueError):
            speed_advantage = 0.0
        if speed_advantage == 0.0:
            continue
        hull.speed_advantage = speed_advantage
        hull.save(update_fields=['speed_advantage'])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0186_rename_win95_theme_label'),
    ]

    operations = [
        migrations.AddField(
            model_name='hulldesign',
            name='speed_advantage',
            field=models.FloatField(default=0.0),
        ),
        migrations.RunPython(
            _backfill_hull_speed_advantage,
            migrations.RunPython.noop,
        ),
    ]
