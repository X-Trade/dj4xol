from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0153_diplomaticcontract_offer_fleet_include_report'),
    ]

    operations = [
        migrations.AddField(
            model_name='salvage',
            name='danger_level',
            field=models.CharField(blank=True, default='', max_length=12),
        ),
    ]
