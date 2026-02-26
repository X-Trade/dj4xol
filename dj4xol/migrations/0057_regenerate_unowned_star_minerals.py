# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from dj4xol import mineral_rules


def regenerate_unowned_star_minerals(apps, schema_editor):
    Star = apps.get_model('dj4xol', 'Star')

    for star in Star.objects.filter(player__isnull=True).only('id'):
        Star.objects.filter(pk=star.pk).update(
            ironium_yield=mineral_rules.random_ironium_yield(),
            boranium_yield=mineral_rules.random_boranium_yield(),
            germanium_yield=mineral_rules.random_germanium_yield(),
            ironium_inventory=mineral_rules.random_surface_ironium_init(),
            boranium_inventory=mineral_rules.random_surface_boranium_init(),
            germanium_inventory=mineral_rules.random_surface_germanium_init(),
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0056_seed_hull_technologies'),
    ]

    operations = [
        migrations.RunPython(regenerate_unowned_star_minerals, noop_reverse),
    ]
