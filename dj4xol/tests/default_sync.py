from django.test import TestCase
import json

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
        self.assertEqual(wormhole.level, 18)
        self.assertEqual(
            json.loads(wormhole.params_json).get('wormhole_fuel_per_ly'), 5.0
        )
        advanced_wormhole = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000112'
        )
        self.assertEqual(advanced_wormhole.category.code, 'METAPHYSICS')
        self.assertEqual(advanced_wormhole.level, 22)
        self.assertEqual(
            json.loads(advanced_wormhole.params_json).get('wormhole_fuel_per_ly'), 4.0
        )
        wormhole_mk3 = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000113'
        )
        self.assertEqual(wormhole_mk3.category.code, 'METAPHYSICS')
        self.assertEqual(wormhole_mk3.level, 26)
        self.assertEqual(
            json.loads(wormhole_mk3.params_json).get('wormhole_fuel_per_ly'), 2.0
        )

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
