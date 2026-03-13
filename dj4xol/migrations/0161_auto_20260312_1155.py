from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0160_add_cloak_fields_and_special_techs'),
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
                    ('SCANNER', 'Scanner'),
                    ('INFRASTRUCTURE', 'Infrastructure'),
                    ('ELECTRICAL', 'Electrical'),
                    ('MECHANICAL', 'Mechanical'),
                    ('BOMB', 'Bomb'),
                    ('SPECIAL', 'Special'),
                    ('OTHER', 'Other'),
                ],
                default='OTHER',
                max_length=16,
            ),
        ),
    ]
