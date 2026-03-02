# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


def forwards(apps, schema_editor):
    FleetOrders = apps.get_model('dj4xol', 'FleetOrders')
    FleetOrders.objects.filter(bomb_until='CONTINUOUS').update(bomb_until='ONCE')


def backwards(apps, schema_editor):
    FleetOrders = apps.get_model('dj4xol', 'FleetOrders')
    FleetOrders.objects.filter(bomb_until='ONCE').update(bomb_until='CONTINUOUS')


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0078_add_bombing_mining_order_params'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name='fleetorders',
            name='bomb_until',
            field=models.CharField(choices=[('COLONISTS_ZERO', 'Until Zero Colonists'), ('DEFENSES_ZERO', 'Until Zero Defenses'), ('ONCE', 'Once')], default='COLONISTS_ZERO', max_length=20),
        ),
    ]
