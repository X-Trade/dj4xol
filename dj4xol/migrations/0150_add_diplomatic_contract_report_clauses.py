from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0149_add_diplomatic_contract_colony_clauses'),
    ]

    operations = [
        migrations.AddField(
            model_name='diplomaticcontract',
            name='offer_report_target_id',
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='diplomaticcontract',
            name='offer_report_target_type',
            field=models.CharField(blank=True, default='', max_length=10),
        ),
        migrations.AddField(
            model_name='diplomaticcontract',
            name='request_report_target_id',
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='diplomaticcontract',
            name='request_report_target_type',
            field=models.CharField(blank=True, default='', max_length=10),
        ),
    ]
