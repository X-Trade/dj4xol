from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0152_add_vague_threat_diplomacy_clause'),
    ]

    operations = [
        migrations.AddField(
            model_name='diplomaticcontract',
            name='offer_fleet_include_report',
            field=models.BooleanField(default=True),
        ),
    ]
