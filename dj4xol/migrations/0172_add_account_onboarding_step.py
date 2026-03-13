from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0171_add_refuel_orders'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='onboarding_step',
            field=models.CharField(
                choices=[
                    ('COMPLETE', 'Complete'),
                    ('THEME', 'Theme'),
                    ('RACE', 'Race'),
                ],
                default='COMPLETE',
                max_length=12,
            ),
        ),
    ]
