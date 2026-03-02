from django.test import TestCase

from ..default_sync import sync_factory_defaults
from ..models import ResearchCategory, ServerRaceType, Technology


class DefaultSyncTest(TestCase):
    def test_sync_creates_and_updates_factory_defaults(self):
        sync_factory_defaults(force=True)

        race = ServerRaceType.objects.get(code='JOAT')
        self.assertTrue(race.name)

        category = ResearchCategory.objects.get(id=1)
        self.assertEqual(category.code, 'ENERGY')

        tech = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000101'
        )
        self.assertEqual(tech.tech_type, 'PROPULSION')
        overdrive = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000110'
        )
        self.assertEqual(overdrive.category.code, 'ENERGY')
        wormhole = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000111'
        )
        self.assertEqual(wormhole.category.code, 'METAPHYSICS')
        self.assertEqual(wormhole.level, 14)

        # Drift values away from fixture defaults.
        race.name = 'Drifted Race'
        race.save(update_fields=['name'])
        category.name = 'Drifted Category'
        category.save(update_fields=['name'])
        tech.name = 'Drifted Tech'
        tech.save(update_fields=['name'])

        sync_factory_defaults(force=True)

        race.refresh_from_db()
        category.refresh_from_db()
        tech.refresh_from_db()
        self.assertEqual(race.name, 'Jack of All Trades')
        self.assertEqual(category.name, 'Energy')
        self.assertEqual(tech.name, 'Improved Warp Coils')
