from django.db import migrations, models


def backfill_server_race_type_display_order(apps, schema_editor):
    ServerRaceType = apps.get_model('dj4xol', 'ServerRaceType')
    ServerRaceType.objects.filter(code='JOAT').update(display_order=0)
    ServerRaceType.objects.exclude(code='JOAT').filter(display_order=0).update(display_order=100)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0138_trim_serverracetype_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='serverracetype',
            name='display_order',
            field=models.IntegerField(default=100),
        ),
        migrations.RunPython(
            backfill_server_race_type_display_order,
            migrations.RunPython.noop,
        ),
    ]
