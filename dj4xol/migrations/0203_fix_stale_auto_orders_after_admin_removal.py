# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.db.models import Q


def _resequence_star_orders(ProductionOrder, star_id):
    orders = list(
        ProductionOrder.objects.filter(star_id=star_id).order_by(
            'added_by_micromanager',
            'position',
            'id',
        )
    )
    for idx, order in enumerate(orders, start=1):
        if int(getattr(order, 'position', 0) or 0) == idx:
            continue
        order.position = idx
        order.save(update_fields=['position'])


def fix_stale_auto_orders_after_admin_removal(apps, schema_editor):
    ProductionOrder = apps.get_model('dj4xol', 'ProductionOrder')

    base_qs = ProductionOrder.objects.filter(
        added_by_micromanager=True,
        star__has_administration=False,
        star__player__isnull=False,
        star__player__is_ai=False,
    )
    star_ids = list(base_qs.values_list('star_id', flat=True).distinct())
    if not star_ids:
        return

    progress_q = (
        Q(completed__gt=0) |
        Q(spent_bp__gt=0) |
        Q(spent_ironium__gt=0) |
        Q(spent_boranium__gt=0) |
        Q(spent_germanium__gt=0) |
        Q(spent_resource_x__gt=0) |
        Q(spent_resource_y__gt=0) |
        Q(spent_resource_z__gt=0)
    )

    base_qs.filter(progress_q).update(added_by_micromanager=False)
    base_qs.exclude(progress_q).delete()

    for star_id in star_ids:
        _resequence_star_orders(ProductionOrder, star_id)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0202_auto_20260327_2019'),
    ]

    operations = [
        migrations.RunPython(
            fix_stale_auto_orders_after_admin_removal,
            migrations.RunPython.noop,
        ),
    ]
