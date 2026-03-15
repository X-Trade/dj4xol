from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0179_replace_terraform_flags_and_sync_defaults'),
    ]

    operations = [
        migrations.AlterField(
            model_name='hulldesignslot',
            name='tech_type',
            field=models.CharField(
                choices=[
                    ('ANY', 'Any'),
                    ('MISC', 'Misc'),
                    ('ANY_WEAPON', 'Any Weapon'),
                    ('SHIELD_OR_ARMOUR', 'Shield or Armour'),
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
                    ('OTHER', 'Other'),
                ],
                default='OTHER',
                max_length=16,
            ),
        ),
    ]
