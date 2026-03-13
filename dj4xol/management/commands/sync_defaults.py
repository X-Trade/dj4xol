from __future__ import unicode_literals

import os

from django.conf import settings
from django.core.management.base import BaseCommand

from dj4xol.default_sync import sync_factory_defaults


class Command(BaseCommand):
    help = 'Sync fixture-backed defaults from defaults.yaml.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fixture',
            dest='fixture',
            default=None,
            help='Path to defaults.yaml (defaults to dj4xol/fixtures/defaults.yaml).',
        )

    def handle(self, *args, **options):
        fixture_path = options.get('fixture')
        if not fixture_path:
            fixture_path = os.path.join(
                settings.BASE_DIR, 'dj4xol', 'fixtures', 'defaults.yaml'
            )

        if not os.path.exists(fixture_path):
            raise RuntimeError('Fixture not found: %s' % fixture_path)

        sync_factory_defaults(force=True, fixture_path=fixture_path)
        self.stdout.write('Synced fixture-backed defaults from %s.' % fixture_path)
