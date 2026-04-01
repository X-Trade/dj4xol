from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0216_auto_20260401_1824'),
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
                    ('GRAVITON', 'Graviton'),
                    ('NOVA', 'Nova'),
                    ('SUPERNOVA', 'Supernova'),
                ],
                default=None,
                max_length=16,
                null=True,
            ),
        ),
    ]
