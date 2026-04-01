from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0215_sync_recent_tech_defaults'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fleet',
            name='has_bombs',
            field=models.CharField(
                blank=True,
                choices=[
                    ('CONVENTIONAL', 'Conventional'),
                    ('NEUTRON', 'Neutron'),
                    ('SMART', 'Smart'),
                    ('NOVA', 'Nova'),
                    ('SUPERNOVA', 'Supernova'),
                ],
                default=None,
                max_length=16,
                null=True,
            ),
        ),
    ]
