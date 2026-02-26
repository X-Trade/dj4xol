import json
import uuid

from django.db import migrations


FRIGATE_HULL_ID = uuid.UUID('00000000-0000-0000-0000-000000000503')


def fix_frigate_hull_thumbnail_class(apps, schema_editor):
    Technology = apps.get_model('dj4xol', 'Technology')
    tech = Technology.objects.filter(id=FRIGATE_HULL_ID).first()
    if not tech:
        return

    try:
        params = json.loads(tech.params_json or '{}')
        if not isinstance(params, dict):
            params = {}
    except (TypeError, ValueError):
        params = {}

    params['hull_thumbnail_class'] = 'frigate'
    tech.params_json = json.dumps(params, sort_keys=True)
    tech.save(update_fields=['params_json'])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0065_raise_existing_players_to_starting_tech_level'),
    ]

    operations = [
        migrations.RunPython(
            fix_frigate_hull_thumbnail_class,
            migrations.RunPython.noop,
        ),
    ]
