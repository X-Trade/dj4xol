from django.db import migrations


def raise_existing_players_to_starting_level(apps, schema_editor):
    Player = apps.get_model('dj4xol', 'Player')
    PlayerResearch = apps.get_model('dj4xol', 'PlayerResearch')
    ResearchCategory = apps.get_model('dj4xol', 'ResearchCategory')

    category_ids = list(
        ResearchCategory.objects.filter(enabled=True).values_list('id', flat=True)
    )
    if not category_ids:
        return

    for player in Player.objects.all().iterator():
        target_level = max(0.0, float(getattr(player, 'starting_tech_level', 3) or 3))
        existing_rows = {
            row.category_id: row
            for row in PlayerResearch.objects.filter(
                player_id=player.id,
                category_id__in=category_ids,
            )
        }

        missing_rows = []
        for category_id in category_ids:
            row = existing_rows.get(category_id)
            if row is None:
                missing_rows.append(PlayerResearch(
                    player_id=player.id,
                    category_id=category_id,
                    current_level=target_level,
                    stored_rp=0.0,
                    allocation_percent=0.0,
                ))
                continue
            if float(row.current_level or 0.0) < target_level:
                row.current_level = target_level
                row.save(update_fields=['current_level'])

        if missing_rows:
            PlayerResearch.objects.bulk_create(missing_rows)


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0064_add_starting_tech_levels'),
    ]

    operations = [
        migrations.RunPython(
            raise_existing_players_to_starting_level,
            migrations.RunPython.noop,
        ),
    ]
