import uuid

from django.db import migrations


HULL_TECH_ROWS = [
    {
        "id": "00000000-0000-0000-0000-000000000501",
        "short_id": "tech00000501",
        "category_id": 5,
        "level": 0,
        "name": "Scout Hull",
        "description": "Baseline scout chassis with minimal holds and tanks.",
        "tech_type": "HULL",
        "params_json": '{"max_cargo_capacity": 50, "max_fuel": 50, "hull_thumbnail_class": "scout", "defense_level": 0.0}',
        "display_order": 210,
        "enabled": True,
    },
    {
        "id": "00000000-0000-0000-0000-000000000502",
        "short_id": "tech00000502",
        "category_id": 5,
        "level": 2,
        "name": "Fighter Hull",
        "description": "Compact combat frame with improved endurance and payload.",
        "tech_type": "HULL",
        "params_json": '{"max_cargo_capacity": 100, "max_fuel": 100, "hull_thumbnail_class": "fighter", "defense_level": 0.0}',
        "display_order": 215,
        "enabled": True,
    },
    {
        "id": "00000000-0000-0000-0000-000000000503",
        "short_id": "tech00000503",
        "category_id": 3,
        "level": 5,
        "name": "Frigate Hull",
        "description": "Armored frigate lines improve battlefield resilience.",
        "tech_type": "HULL",
        "params_json": '{"max_cargo_capacity": 200, "max_fuel": 100, "hull_thumbnail_class": "fighter", "defense_level": 1.0}',
        "display_order": 220,
        "enabled": True,
    },
    {
        "id": "00000000-0000-0000-0000-000000000504",
        "short_id": "tech00000504",
        "category_id": 5,
        "level": 6,
        "name": "Freighter Hull",
        "description": "Expanded commercial bays and reinforced tankage for bulk transport.",
        "tech_type": "HULL",
        "params_json": '{"max_cargo_capacity": 400, "max_fuel": 200, "hull_thumbnail_class": "freighter", "defense_level": 2.0}',
        "display_order": 225,
        "enabled": True,
    },
    {
        "id": "00000000-0000-0000-0000-000000000505",
        "short_id": "tech00000505",
        "category_id": 3,
        "level": 8,
        "name": "Tanker Hull",
        "description": "Long-haul fuel architecture sacrifices protection for range.",
        "tech_type": "HULL",
        "params_json": '{"max_cargo_capacity": 400, "max_fuel": 800, "hull_thumbnail_class": "tanker", "defense_level": -1.0}',
        "display_order": 230,
        "enabled": True,
    },
    {
        "id": "00000000-0000-0000-0000-000000000506",
        "short_id": "tech00000506",
        "category_id": 5,
        "level": 10,
        "name": "Capital Hull",
        "description": "Capital-scale battlesteel spine with heavy defensive compartmentalisation.",
        "tech_type": "HULL",
        "params_json": '{"max_cargo_capacity": 1000, "max_fuel": 1000, "hull_thumbnail_class": "capital", "defense_level": 9.0}',
        "display_order": 235,
        "enabled": True,
    },
    {
        "id": "00000000-0000-0000-0000-000000000507",
        "short_id": "tech00000507",
        "category_id": 4,
        "level": 12,
        "name": "City Hull",
        "description": "Metaphasic cityship architecture supports colossal stores and shielding.",
        "tech_type": "HULL",
        "params_json": '{"max_cargo_capacity": 10000, "max_fuel": 10000, "hull_thumbnail_class": "city", "defense_level": 12.0}',
        "display_order": 240,
        "enabled": True,
    },
]


def seed_hull_technologies(apps, schema_editor):
    Technology = apps.get_model("dj4xol", "Technology")
    for row in HULL_TECH_ROWS:
        row = dict(row)
        tech_id = uuid.UUID(row.pop("id"))
        Technology.objects.update_or_create(id=tech_id, defaults=row)


class Migration(migrations.Migration):

    dependencies = [
        ("dj4xol", "0055_add_hull_tech_type"),
    ]

    operations = [
        migrations.RunPython(seed_hull_technologies, migrations.RunPython.noop),
    ]
