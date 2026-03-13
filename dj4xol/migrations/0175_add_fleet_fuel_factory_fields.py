from django.db import migrations, models


def backfill_fleet_fuel_factory_fields(apps, schema_editor):
    Fleet = apps.get_model('dj4xol', 'Fleet')
    Fleet.objects.filter(
        has_fuel_factory=True,
        fuel_factory_mg_per_year=0.0,
    ).update(
        fuel_factory_mg_per_year=1.0,
        fuel_factory_max_warp=0,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0174_add_account_email_verification'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleet',
            name='fuel_factory_max_warp',
            field=models.IntegerField(default=-1),
        ),
        migrations.AddField(
            model_name='fleet',
            name='fuel_factory_mg_per_year',
            field=models.FloatField(default=0.0),
        ),
        migrations.RunPython(
            backfill_fleet_fuel_factory_fields,
            migrations.RunPython.noop,
        ),
    ]
