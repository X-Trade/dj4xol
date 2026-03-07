from __future__ import unicode_literals

import os
import uuid

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand

from dj4xol.models import ResearchCategory, Technology


class Command(BaseCommand):
    help = 'Sync research categories and technologies from defaults.yaml.'

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

        with open(fixture_path, 'r') as handle:
            rows = yaml.safe_load(handle) or []

        category_count = 0
        tech_count = 0

        for row in rows:
            if row.get('model') != 'dj4xol.ResearchCategory':
                continue
            fields = dict(row.get('fields') or {})
            pk = row.get('pk')
            if pk is None:
                continue
            ResearchCategory.objects.update_or_create(
                id=int(pk),
                defaults=fields,
            )
            category_count += 1

        for row in rows:
            if row.get('model') != 'dj4xol.Technology':
                continue
            fields = dict(row.get('fields') or {})
            pk = row.get('pk')
            if not pk:
                continue
            if 'category' in fields and 'category_id' not in fields:
                fields['category_id'] = fields.pop('category')
            tech_id = uuid.UUID(str(pk))
            technology = Technology.objects.filter(id=tech_id).first()
            if technology is None:
                short_id = fields.get('short_id')
                if short_id:
                    technology = Technology.objects.filter(short_id=short_id).first()
            if technology is None:
                Technology.objects.create(id=tech_id, **fields)
            else:
                for key, value in fields.items():
                    setattr(technology, key, value)
                technology.save()
            tech_count += 1

        self.stdout.write(
            'Synced %s research categories and %s technologies.' % (
                category_count,
                tech_count,
            )
        )
