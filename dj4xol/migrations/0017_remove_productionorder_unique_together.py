# -*- coding: utf-8 -*-
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0016_auto_20260202_2001'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='productionorder',
            unique_together=set(),
        ),
    ]
