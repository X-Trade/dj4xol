from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0170_add_fleet_order_last_contact_year'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleetorders',
            name='transfer_fuel',
            field=models.FloatField(default=0.0),
        ),
        migrations.AlterField(
            model_name='fleetorders',
            name='order_type',
            field=models.CharField(
                choices=[
                    ('MOVE', 'Move'),
                    ('INTERCEPT', 'Intercept'),
                    ('REFUEL', 'Refuel'),
                    ('TRANSFER', 'Transfer'),
                    ('GIVE', 'Transfer Fleet'),
                    ('COLONISE', 'Colonise'),
                    ('BOMB', 'Bomb'),
                    ('REMOTEMINE', 'Remote Mine'),
                    ('MERGE', 'Merge'),
                    ('SCUTTLE', 'Scuttle'),
                    ('PATROL', 'Patrol'),
                ],
                default='MOVE',
                max_length=10,
            ),
        ),
    ]
