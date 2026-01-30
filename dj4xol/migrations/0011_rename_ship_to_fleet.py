# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0010_star_base_capacity'),
    ]

    operations = [
        # Rename Ship model to Fleet
        migrations.RenameModel(
            old_name='Ship',
            new_name='Fleet',
        ),
        # Rename ShipOrders model to FleetOrders
        migrations.RenameModel(
            old_name='ShipOrders',
            new_name='FleetOrders',
        ),
        # Rename foreign key field ship -> fleet in FleetOrders
        migrations.RenameField(
            model_name='fleetorders',
            old_name='ship',
            new_name='fleet',
        ),
        # Rename foreign key field target_ship -> target_fleet in FleetOrders
        migrations.RenameField(
            model_name='fleetorders',
            old_name='target_ship',
            new_name='target_fleet',
        ),
        # Update related_name on Game -> Fleet (ships -> fleets)
        migrations.AlterField(
            model_name='fleet',
            name='game',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='fleets',
                to='dj4xol.Game',
            ),
        ),
        # Update related_name on Player -> Fleet (ships -> fleets)
        migrations.AlterField(
            model_name='fleet',
            name='player',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='fleets',
                to='dj4xol.Player',
            ),
        ),
    ]
