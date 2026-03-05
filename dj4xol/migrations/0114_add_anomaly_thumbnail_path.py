from django.db import migrations, models


ANOMALY_TYPE_TO_FOLDER = {
    'NEBULA': 'nebula',
    'COMET': 'comet',
    'RIFT': 'rift',
    'BLACK_HOLE': 'blackhole',
    'WORMHOLE': 'wormhole',
    'ANOMALY': 'nebula',
}


def _pick_thumbnail(anomaly_type):
    try:
        from dj4xol.anomaly_thumbnail_catalog import (
            ANOMALY_THUMBNAILS_BY_TYPE,
            ALL_ANOMALY_THUMBNAILS,
        )
    except Exception:
        return ''
    folder = ANOMALY_TYPE_TO_FOLDER.get((anomaly_type or '').upper())
    candidates = ANOMALY_THUMBNAILS_BY_TYPE.get(folder) if folder else None
    if not candidates:
        candidates = ALL_ANOMALY_THUMBNAILS
    if not candidates:
        return ''
    import random
    return random.choice(candidates)


def assign_anomaly_thumbnails(apps, schema_editor):
    Anomaly = apps.get_model('dj4xol', 'Anomaly')
    for anomaly in Anomaly.objects.filter(thumbnail_path=''):
        chosen = _pick_thumbnail(anomaly.anomaly_type)
        if chosen:
            anomaly.thumbnail_path = chosen
            anomaly.save(update_fields=['thumbnail_path'])


class Migration(migrations.Migration):
    dependencies = [
        ('dj4xol', '0113_add_remotemine_focus'),
    ]

    operations = [
        migrations.AddField(
            model_name='anomaly',
            name='thumbnail_path',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.RunPython(assign_anomaly_thumbnails, migrations.RunPython.noop),
    ]
