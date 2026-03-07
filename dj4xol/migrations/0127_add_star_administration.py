from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0126_sync_tech_rebalance_from_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='star',
            name='has_administration',
            field=models.BooleanField(default=False),
        ),
    ]
