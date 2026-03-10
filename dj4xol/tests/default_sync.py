from django.test import TestCase
import json
import uuid

from ..default_sync import sync_factory_defaults
from ..models import (
    ResearchCategory,
    ResearchLevelPrerequisite,
    ServerRaceType,
    Technology,
)


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
        self.assertEqual(wormhole.level, 19)
        self.assertEqual(
            json.loads(wormhole.params_json).get('wormhole_fuel_per_ly'), 5.0
        )
        advanced_wormhole = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000112'
        )
        self.assertEqual(advanced_wormhole.category.code, 'METAPHYSICS')
        self.assertEqual(advanced_wormhole.level, 23)
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
        phased_disruptor = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000206'
        )
        self.assertEqual(phased_disruptor.category.code, 'ENERGY')
        self.assertEqual(phased_disruptor.level, 6)
        targeting_computer = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000212'
        )
        self.assertEqual(targeting_computer.category.code, 'ELECTRONICS')
        self.assertEqual(targeting_computer.level, 5)
        scanner_v = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000704'
        )
        self.assertEqual(
            json.loads(scanner_v.params_json),
            {'basic_scanner_range': 40, 'advanced_scanner_range': 15},
        )
        colony_scanner_v = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000724'
        )
        self.assertEqual(
            json.loads(colony_scanner_v.params_json),
            {'basic_scanner_range': 50, 'advanced_scanner_range': 10},
        )
        colony_scanner_vi = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000725'
        )
        self.assertEqual(
            json.loads(colony_scanner_vi.params_json),
            {'basic_scanner_range': 70, 'advanced_scanner_range': 15},
        )
        smart_bombs = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000604'
        )
        self.assertEqual(smart_bombs.level, 12)
        self.assertEqual(
            json.loads(smart_bombs.params_json).get('race_type'), 'not WAR'
        )
        nova_bombs = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000605'
        )
        self.assertEqual(nova_bombs.level, 21)
        prototype_wormhole = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000114'
        )
        self.assertEqual(
            json.loads(prototype_wormhole.params_json).get('race_type'), 'SCI'
        )
        advanced_remote_miners = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000602'
        )
        self.assertEqual(
            json.loads(advanced_remote_miners.params_json).get('race_type'),
            'has has_advanced_remoteminers',
        )
        warp_8 = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000106'
        )
        self.assertEqual(warp_8.level, 9)
        warp_9 = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000107'
        )
        self.assertEqual(warp_9.level, 10)
        warp_10 = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000108'
        )
        self.assertEqual(warp_10.level, 13)
        planetary_disruptors = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000403'
        )
        self.assertEqual(planetary_disruptors.category.code, 'CONSTRUCTION')
        self.assertEqual(planetary_disruptors.level, 6)
        planetary_disruptor_gate = ResearchLevelPrerequisite.objects.get(
            category__code='CONSTRUCTION',
            level=6,
            requires_category__code='ENERGY',
        )
        self.assertEqual(planetary_disruptor_gate.min_level, 5)

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

    def test_sync_restores_fixture_backed_research_prerequisites(self):
        sync_factory_defaults(force=True)

        prerequisite = ResearchLevelPrerequisite.objects.get(
            category__code='CONSTRUCTION',
            level=6,
            requires_category__code='ENERGY',
        )
        prerequisite.min_level = 2
        prerequisite.save(update_fields=['min_level'])

        sync_factory_defaults(force=True)

        prerequisite.refresh_from_db()
        self.assertEqual(prerequisite.min_level, 5)

    def test_sync_reconciles_technology_by_short_id_when_uuid_differs(self):
        sync_factory_defaults(force=True)

        original = Technology.objects.get(short_id='tech00000206')
        original.delete()
        drifted_id = uuid.uuid4()
        Technology.objects.create(
            id=drifted_id,
            short_id='tech00000206',
            category_id=2,
            level=99,
            name='Old Phased Disruptor',
            description='Drifted',
            tech_type='ENERGY_WEAPON',
            params_json='{"offense_level": 0.01}',
            display_order=1,
            enabled=True,
        )

        sync_factory_defaults(force=True)

        technologies = list(Technology.objects.filter(short_id='tech00000206'))
        self.assertEqual(len(technologies), 1)
        technology = technologies[0]
        self.assertEqual(technology.id, drifted_id)
        self.assertEqual(technology.name, 'Phased Disruptor')
        self.assertEqual(technology.category.code, 'ENERGY')
        self.assertEqual(technology.level, 6)

    def test_propulsion_defaults_keep_early_overmax_penalties_high_until_warp_8(self):
        sync_factory_defaults(force=True)

        warp2 = Technology.objects.get(id='00000000-0000-0000-0000-000000000100')
        warp7 = Technology.objects.get(id='00000000-0000-0000-0000-000000000105')
        warp8 = Technology.objects.get(id='00000000-0000-0000-0000-000000000106')
        warp9 = Technology.objects.get(id='00000000-0000-0000-0000-000000000107')

        warp2_penalty = json.loads(warp2.params_json).get('overmax_fuel_penalty')
        warp7_penalty = json.loads(warp7.params_json).get('overmax_fuel_penalty')
        warp8_penalty = json.loads(warp8.params_json).get('overmax_fuel_penalty')
        warp9_penalty = json.loads(warp9.params_json).get('overmax_fuel_penalty')

        self.assertGreater(warp2_penalty, warp7_penalty)
        self.assertGreater(warp7_penalty, 1.0)
        self.assertLess(warp8_penalty, warp7_penalty)
        self.assertLessEqual(warp9_penalty, warp8_penalty)
