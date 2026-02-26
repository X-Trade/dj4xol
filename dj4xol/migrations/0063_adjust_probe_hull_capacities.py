import json
import uuid

from django.db import migrations


PROBE_HULL_ID = uuid.UUID('00000000-0000-0000-0000-000000000500')


def adjust_probe_hull_capacities(apps, schema_editor):
    Technology = apps.get_model('dj4xol', 'Technology')
    tech = Technology.objects.filter(id=PROBE_HULL_ID).first()
    if not tech:
        return

    try:
        params = json.loads(tech.params_json or '{}')
        if not isinstance(params, dict):
            params = {}
    except (TypeError, ValueError):
        params = {}

    params['max_cargo_capacity'] = 10
    params['max_fuel'] = 40
    tech.params_json = json.dumps(params, sort_keys=True)
    tech.save(update_fields=['params_json'])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0062_seed_level0_propulsion'),
    ]

    operations = [
        migrations.RunPython(adjust_probe_hull_capacities, migrations.RunPython.noop),
    ]
