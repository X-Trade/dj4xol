from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0140_remove_serverracetype_legacy_habitability_fields'),
    ]

    operations = [
        migrations.RenameField(
            model_name='serverracetype',
            old_name='starting_planets',
            new_name='starting_colonies',
        ),
    ]
