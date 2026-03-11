# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


def backfill_offer_condition_type(apps, schema_editor):
    DiplomaticContract = apps.get_model('dj4xol', 'DiplomaticContract')
    DiplomaticContract.objects.filter(
        temperature='DEMAND',
        offer_condition_type='EXCHANGE',
    ).update(offer_condition_type='OR_ELSE')


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0147_add_diplomatic_contracts_and_technology_grants'),
    ]

    operations = [
        migrations.AddField(
            model_name='diplomaticcontract',
            name='offer_condition_type',
            field=models.CharField(
                choices=[('EXCHANGE', 'In Exchange For'), ('OR_ELSE', 'Or Else')],
                default='EXCHANGE',
                max_length=16,
            ),
        ),
        migrations.RunPython(backfill_offer_condition_type, migrations.RunPython.noop),
    ]
