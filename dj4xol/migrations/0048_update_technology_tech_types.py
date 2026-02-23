from django.db import migrations, models


def migrate_weapon_types(apps, schema_editor):
    Technology = apps.get_model('dj4xol', 'Technology')
    weapon_rows = Technology.objects.filter(tech_type='WEAPON')
    for tech in weapon_rows.iterator():
        name = (tech.name or '').lower()
        if 'torpedo' in name or 'targeting computer' in name:
            tech.tech_type = 'TORPEDO'
        else:
            tech.tech_type = 'ENERGY_WEAPON'
        tech.save(update_fields=['tech_type'])


def reverse_migrate_weapon_types(apps, schema_editor):
    Technology = apps.get_model('dj4xol', 'Technology')
    Technology.objects.filter(
        tech_type__in=['ENERGY_WEAPON', 'TORPEDO']
    ).update(tech_type='WEAPON')


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0047_update_surface_mineral_defaults'),
    ]

    operations = [
        migrations.RunPython(
            migrate_weapon_types,
            reverse_migrate_weapon_types,
        ),
        migrations.AlterField(
            model_name='technology',
            name='tech_type',
            field=models.CharField(
                choices=[
                    ('PROPULSION', 'Propulsion'),
                    ('ENERGY_WEAPON', 'Energy Weapon'),
                    ('TORPEDO', 'Torpedo'),
                    ('SHIELD', 'Shield'),
                    ('ARMOUR', 'Armour'),
                    ('OTHER', 'Other'),
                ],
                default='OTHER',
                max_length=16,
            ),
        ),
    ]
