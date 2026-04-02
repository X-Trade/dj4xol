from django.db import migrations


LATE_GAME_RP_COSTS = {
    19: 300000,
    20: 480000,
    21: 720000,
    22: 1000000,
    23: 1300000,
    24: 1600000,
    25: 1825000,
    26: 2000000,
}


def flatten_endgame_research_rp_curve(apps, schema_editor):
    DefaultResearchLevelRequirement = apps.get_model(
        'dj4xol',
        'DefaultResearchLevelRequirement',
    )
    ResearchLevelRequirement = apps.get_model(
        'dj4xol',
        'ResearchLevelRequirement',
    )

    for level, rp_cost in sorted(LATE_GAME_RP_COSTS.items()):
        DefaultResearchLevelRequirement.objects.update_or_create(
            level=level,
            defaults={'rp_cost': int(rp_cost)},
        )
        ResearchLevelRequirement.objects.filter(level=level).update(
            rp_cost=int(rp_cost)
        )


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0223_sync_recent_tech_defaults'),
    ]

    operations = [
        migrations.RunPython(
            flatten_endgame_research_rp_curve,
            migrations.RunPython.noop,
        ),
    ]
