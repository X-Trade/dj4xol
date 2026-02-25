from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0054_add_fleet_fuel'),
    ]

    operations = [
        migrations.AlterField(
            model_name='technology',
            name='tech_type',
            field=models.CharField(
                choices=[
                    ('PROPULSION', 'Propulsion'),
                    ('HULL', 'Hull'),
                    ('ENERGY_WEAPON', 'Energy Weapon'),
                    ('TORPEDO', 'Torpedo'),
                    ('SHIELD', 'Shield'),
                    ('ARMOUR', 'Armour'),
                    ('INFRASTRUCTURE', 'Infrastructure'),
                    ('OTHER', 'Other'),
                ],
                default='OTHER',
                max_length=16,
            ),
        ),
    ]
