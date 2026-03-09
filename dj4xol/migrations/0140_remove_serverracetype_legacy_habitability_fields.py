from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0139_add_serverracetype_display_order'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='serverracetype',
            name='gravity_center',
        ),
        migrations.RemoveField(
            model_name='serverracetype',
            name='gravity_width',
        ),
        migrations.RemoveField(
            model_name='serverracetype',
            name='temperature_center',
        ),
        migrations.RemoveField(
            model_name='serverracetype',
            name='temperature_width',
        ),
        migrations.RemoveField(
            model_name='serverracetype',
            name='radiation_center',
        ),
        migrations.RemoveField(
            model_name='serverracetype',
            name='radiation_width',
        ),
    ]
