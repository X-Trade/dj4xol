# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def copy_pending_default_stances(apps, schema_editor):
    Player = apps.get_model('dj4xol', 'Player')
    valid_stances = {'HOSTILE', 'COLD', 'NEUTRAL', 'WARM', 'ALLIED'}
    for player in Player.objects.all():
        pending = getattr(player, 'pending_default_diplomatic_stance', None)
        if pending in valid_stances and player.default_diplomatic_stance != pending:
            player.default_diplomatic_stance = pending
            player.save(update_fields=['default_diplomatic_stance'])


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0227_auto_20260406_1325'),
    ]

    operations = [
        migrations.RunPython(copy_pending_default_stances, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='player',
            name='pending_default_diplomatic_stance',
        ),
    ]
