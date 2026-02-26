import json
import uuid

from django.db import migrations


PROPULSION_FUEL_DEFAULTS = {
    # Early drives: less efficient and harder overmax burns.
    '00000000-0000-0000-0000-000000000101': {'fuel_efficiency': 0.70, 'overmax_fuel_penalty': 1.25},
    '00000000-0000-0000-0000-000000000102': {'fuel_efficiency': 0.78, 'overmax_fuel_penalty': 1.20},
    '00000000-0000-0000-0000-000000000103': {'fuel_efficiency': 0.86, 'overmax_fuel_penalty': 1.12},
    '00000000-0000-0000-0000-000000000104': {'fuel_efficiency': 0.94, 'overmax_fuel_penalty': 1.05},
    '00000000-0000-0000-0000-000000000105': {'fuel_efficiency': 1.00, 'overmax_fuel_penalty': 1.00},
    '00000000-0000-0000-0000-000000000106': {'fuel_efficiency': 1.10, 'overmax_fuel_penalty': 0.92},
    '00000000-0000-0000-0000-000000000107': {'fuel_efficiency': 1.18, 'overmax_fuel_penalty': 0.86},
    # Requested edge cases: high-warp unlocks with poor efficiency.
    '00000000-0000-0000-0000-000000000108': {'fuel_efficiency': 0.88, 'overmax_fuel_penalty': 1.55},
    '00000000-0000-0000-0000-000000000109': {'fuel_efficiency': 1.28, 'overmax_fuel_penalty': 0.80},
    '00000000-0000-0000-0000-000000000110': {'fuel_efficiency': 0.82, 'overmax_fuel_penalty': 1.75},
}


def seed_propulsion_fuel_params(apps, schema_editor):
    Technology = apps.get_model('dj4xol', 'Technology')

    for tech_id, additions in PROPULSION_FUEL_DEFAULTS.items():
        tech = Technology.objects.filter(id=uuid.UUID(tech_id)).first()
        if tech is None:
            continue

        try:
            params = json.loads(tech.params_json or '{}')
        except (TypeError, ValueError):
            params = {}
        if not isinstance(params, dict):
            params = {}

        changed = False
        for key, value in additions.items():
            if key not in params:
                params[key] = value
                changed = True

        if changed:
            tech.params_json = json.dumps(params, sort_keys=True)
            tech.save(update_fields=['params_json'])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0058_add_fleet_fuel_efficiency'),
    ]

    operations = [
        migrations.RunPython(seed_propulsion_fuel_params, migrations.RunPython.noop),
    ]
