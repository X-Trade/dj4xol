from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0137_add_pending_diplomacy_snapshot_fields'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='serverracetype',
            name='starting_population',
        ),
        migrations.RemoveField(
            model_name='serverracetype',
            name='starting_planet_has_massdriver',
        ),
        migrations.RemoveField(
            model_name='serverracetype',
            name='metalurgy_multiplier',
        ),
        migrations.RemoveField(
            model_name='serverracetype',
            name='persuasion_multiplier',
        ),
        migrations.RemoveField(
            model_name='serverracetype',
            name='chance_of_scantheft',
        ),
        migrations.RemoveField(
            model_name='serverracetype',
            name='requires_space_station',
        ),
        migrations.RemoveField(
            model_name='serverracetype',
            name='starting_research_points',
        ),
    ]
