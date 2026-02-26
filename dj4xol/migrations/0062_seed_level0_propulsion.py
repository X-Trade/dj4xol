import uuid

from django.db import migrations


LEVEL0_PROPULSION_TECH = {
    'id': '00000000-0000-0000-0000-000000000100',
    'short_id': 'tech00000100',
    'category_id': 1,
    'level': 0,
    'name': 'Prototype Warp Coils',
    'description': 'First-generation warp drive with poor fuel economy and conservative safety margins.',
    'tech_type': 'PROPULSION',
    'params_json': '{"max_warp_speed": 2, "fuel_efficiency": 0.58, "overmax_fuel_penalty": 1.40}',
    'display_order': 5,
    'enabled': True,
}


def seed_level0_propulsion(apps, schema_editor):
    Technology = apps.get_model('dj4xol', 'Technology')
    values = dict(LEVEL0_PROPULSION_TECH)
    tech_id = uuid.UUID(values.pop('id'))
    Technology.objects.update_or_create(id=tech_id, defaults=values)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0061_seed_level0_fleet_techs'),
    ]

    operations = [
        migrations.RunPython(seed_level0_propulsion, migrations.RunPython.noop),
    ]
