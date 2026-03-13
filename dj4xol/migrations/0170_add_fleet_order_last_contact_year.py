from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0169_sync_cloak_branch_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='fleetorders',
            name='last_contact_year',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
