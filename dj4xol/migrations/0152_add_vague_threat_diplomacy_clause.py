from __future__ import unicode_literals

from django.db import migrations, models


CLAUSE_CHOICES = [
    ('NOTHING', 'Nothing'),
    ('TECHNOLOGY', 'Technology'),
    ('STANCE', 'Stance'),
    ('RESOURCE_TO_WORLD', 'Resources To World'),
    ('RESOURCE_ON_GIVEN_FLEET', 'Resources On Given Fleet'),
    ('FLEET_BY_SHIP_COUNT', 'Fleet By Ship Count'),
    ('SPECIFIC_FLEET', 'Specific Fleet'),
    ('SPECIFIC_COLONY', 'Specific Colony'),
    ('REPORT', 'Report'),
    ('VAGUE_THREAT', 'Vague Threat'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0151_auto_20260311_1127'),
    ]

    operations = [
        migrations.AlterField(
            model_name='diplomaticcontract',
            name='offer_clause_type',
            field=models.CharField(choices=CLAUSE_CHOICES, default='NOTHING', max_length=24),
        ),
        migrations.AlterField(
            model_name='diplomaticcontract',
            name='request_clause_type',
            field=models.CharField(choices=CLAUSE_CHOICES, default='NOTHING', max_length=24),
        ),
    ]
