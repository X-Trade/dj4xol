# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def backfill_fleetorder_target_index(apps, schema_editor):
    FleetOrders = apps.get_model('dj4xol', 'FleetOrders')
    Star = apps.get_model('dj4xol', 'Star')
    Fleet = apps.get_model('dj4xol', 'Fleet')
    Salvage = apps.get_model('dj4xol', 'Salvage')
    Anomaly = apps.get_model('dj4xol', 'Anomaly')

    for order in FleetOrders.objects.all():
        target_kind = None
        target_short_id = None

        if order.target_star_id:
            star = Star.objects.filter(id=order.target_star_id).first()
            if star is not None:
                target_kind = 'OBJECT'
                target_short_id = star.short_id
        elif order.target_fleet_id:
            fleet = Fleet.objects.filter(id=order.target_fleet_id).first()
            if fleet is not None:
                target_kind = 'OBJECT'
                target_short_id = fleet.short_id
        elif order.target_salvage_id:
            salvage = Salvage.objects.filter(id=order.target_salvage_id).first()
            if salvage is not None:
                target_kind = 'OBJECT'
                target_short_id = salvage.short_id
        elif order.target_short_id:
            sid = str(order.target_short_id).strip().lower()
            if sid:
                obj = (
                    Star.objects.filter(game=order.game, short_id=sid).first()
                    or Fleet.objects.filter(game=order.game, short_id=sid).first()
                    or Salvage.objects.filter(game=order.game, short_id=sid).first()
                    or Anomaly.objects.filter(game=order.game, short_id=sid).first()
                )
                if obj is not None:
                    target_kind = 'OBJECT'
                    target_short_id = obj.short_id

        if target_kind is None and order.x is not None and order.y is not None:
            target_kind = 'SPACE'
            target_short_id = None

        FleetOrders.objects.filter(id=order.id).update(
            target_kind=target_kind,
            target_short_id=target_short_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0087_auto_20260302_1747'),
    ]

    operations = [
        migrations.RunPython(backfill_fleetorder_target_index, migrations.RunPython.noop),
    ]
