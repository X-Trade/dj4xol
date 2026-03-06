"""Management command for scheduled turn generation.

Run via cron every 10 minutes or so:
    */10 * * * * cd /path/to/project && python manage.py generate_turns
"""
import logging

from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q
from django.utils import timezone

from dj4xol.models import Game, ServerSettings
from dj4xol.email_rollups import send_message_rollups
from dj4xol.turn import GameTurn

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Generate turns for games that are overdue for scheduled generation'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='List games that would be processed without generating turns',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now = timezone.now()

        # Find timed games (HOURLY, DAILY, WEEKLY) that are overdue
        timed_games = Game.objects.filter(
            ended=False,
            is_generating=False,
            next_generation__isnull=False,
            next_generation__lte=now,
        ).exclude(
            players__isnull=True
        ).distinct()

        # Check if quorum games should be processed by cronjob
        quorum_mode = ServerSettings.get('quorum_generation_mode', 'webserver')
        process_quorum = (quorum_mode == 'cronjob')

        quorum_games = Game.objects.none()
        if process_quorum:
            # Find QUORUM games where all players have turned in
            # Annotate with player counts and filter where all are turned in
            quorum_games = Game.objects.filter(
                turn_scheme='QUORUM',
                ended=False,
                is_generating=False,
            ).annotate(
                total_players=Count('players', filter=Q(players__defeated=False)),
                turned_in_players=Count(
                    'players', filter=Q(players__turned_in=True, players__defeated=False)
                )
            ).filter(
                total_players__gt=0,
                total_players=F('turned_in_players')
            )

        # Combine the querysets
        all_games = list(timed_games) + list(quorum_games)
        # Remove duplicates (in case a game somehow matches both)
        seen_ids = set()
        games_to_process = []
        for game in all_games:
            if game.id not in seen_ids:
                seen_ids.add(game.id)
                games_to_process.append(game)

        game_count = len(games_to_process)

        if game_count == 0:
            self.stdout.write('No games due for turn generation.')
            send_message_rollups(dry_run=dry_run, stdout=self.stdout)
            return

        timed_count = timed_games.count()
        quorum_count = len(games_to_process) - timed_count
        self.stdout.write(
            f'Found {game_count} game(s) due for turn generation '
            f'({timed_count} timed, {quorum_count} quorum).'
        )

        success_count = 0
        failure_count = 0

        for game in games_to_process:
            reason = 'quorum' if game.turn_scheme == 'QUORUM' else 'scheduled'
            if dry_run:
                self.stdout.write(
                    f'  [DRY RUN] Would generate turn for: {game.name} '
                    f'(id={game.short_id}, year={game.year}, reason={reason})'
                )
                continue

            try:
                self.stdout.write(
                    f'  Generating turn for: {game.name} '
                    f'(id={game.short_id}, reason={reason})'
                )
                turn = GameTurn(game)
                turn.generate_turn()
                success_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'    Success: {game.name} now at year {game.year}'
                    )
                )
            except Exception as e:
                failure_count += 1
                error_msg = (
                    f'Failed to generate turn for {game.name} '
                    f'(id={game.short_id}): {e}'
                )
                self.stdout.write(self.style.ERROR(f'    {error_msg}'))
                logger.exception(error_msg)

                # Ensure is_generating is reset if it got stuck
                try:
                    game.refresh_from_db()
                    if game.is_generating:
                        game.is_generating = False
                        game.save(update_fields=['is_generating'])
                        self.stdout.write(
                            self.style.WARNING(
                                f'    Reset is_generating flag for {game.name}'
                            )
                        )
                except Exception as reset_error:
                    logger.exception(
                        f'Failed to reset is_generating for {game.name}: {reset_error}'
                    )

        send_message_rollups(dry_run=dry_run, stdout=self.stdout)

        if not dry_run:
            self.stdout.write(
                f'Turn generation complete: '
                f'{success_count} succeeded, {failure_count} failed.'
            )
