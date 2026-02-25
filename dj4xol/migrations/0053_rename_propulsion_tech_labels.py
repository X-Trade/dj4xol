# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def forwards(apps, schema_editor):
    Technology = apps.get_model('dj4xol', 'Technology')
    updates = [
        (
            'tech00000106',
            'Interstellar Ram Scoops',
            'Fuel-scoop geometry stabilizes long-range high-warp transits.',
        ),
        (
            'tech00000109',
            'Inertial Minimizer',
            'High-precision inertial damping lowers frame stress and maintains reliable Warp 10 transit.',
        ),
    ]
    for short_id, name, description in updates:
        Technology.objects.filter(short_id=short_id).update(
            name=name,
            description=description,
        )


def backwards(apps, schema_editor):
    Technology = apps.get_model('dj4xol', 'Technology')
    updates = [
        (
            'tech00000106',
            'Relativistic Drift Compensation',
            'Navigation matrices compensate relativistic drift in deep-warp corridors.',
        ),
        (
            'tech00000109',
            'Orbital Lane Catapult Network',
            'Construction-grade catapult lanes synchronize departure vectors for reliable Warp 10 transit.',
        ),
    ]
    for short_id, name, description in updates:
        Technology.objects.filter(short_id=short_id).update(
            name=name,
            description=description,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0052_fleet_thumbnail_path'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
