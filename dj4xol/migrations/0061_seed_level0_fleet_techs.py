import uuid

from django.db import migrations


LEVEL0_TECH_ROWS = [
    {
        'id': '00000000-0000-0000-0000-000000000200',
        'short_id': 'tech00000200',
        'category_id': 1,
        'level': 0,
        'name': 'Gauss Gun',
        'description': 'A primitive mass-driver weapon with limited penetration.',
        'tech_type': 'ENERGY_WEAPON',
        'params_json': '{"offense_level": 0.10}',
        'display_order': 45,
        'enabled': True,
    },
    {
        'id': '00000000-0000-0000-0000-000000000300',
        'short_id': 'tech00000300',
        'category_id': 3,
        'level': 0,
        'name': 'Light Composite Plating',
        'description': 'Baseline hull reinforcement with modest defensive value.',
        'tech_type': 'ARMOUR',
        'params_json': '{"defense_level": 0.10}',
        'display_order': 115,
        'enabled': True,
    },
    {
        'id': '00000000-0000-0000-0000-000000000500',
        'short_id': 'tech00000500',
        'category_id': 5,
        'level': 0,
        'name': 'Probe Hull',
        'description': 'Minimal autonomous hull for expendable reconnaissance craft.',
        'tech_type': 'HULL',
        'params_json': '{"max_cargo_capacity": 25, "max_fuel": 25, "hull_thumbnail_class": "probe", "defense_level": -1.0, "offense_level": -0.5}',
        'display_order': 205,
        'enabled': True,
    },
    {
        'id': '00000000-0000-0000-0000-000000000501',
        'short_id': 'tech00000501',
        'category_id': 5,
        'level': 1,
        'name': 'Scout Hull',
        'description': 'Baseline scout chassis with minimal holds and tanks.',
        'tech_type': 'HULL',
        'params_json': '{"max_cargo_capacity": 50, "max_fuel": 50, "hull_thumbnail_class": "scout", "defense_level": -0.4}',
        'display_order': 210,
        'enabled': True,
    },
]


def seed_level0_fleet_techs(apps, schema_editor):
    Technology = apps.get_model('dj4xol', 'Technology')

    for row in LEVEL0_TECH_ROWS:
        values = dict(row)
        tech_id = uuid.UUID(values.pop('id'))
        Technology.objects.update_or_create(id=tech_id, defaults=values)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0060_sync_tech_tree_from_fixtures'),
    ]

    operations = [
        migrations.RunPython(seed_level0_fleet_techs, migrations.RunPython.noop),
    ]
