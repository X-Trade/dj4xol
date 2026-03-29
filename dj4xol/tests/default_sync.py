from django.test import TestCase
from io import StringIO
import json
import uuid

from django.core.management import call_command
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
        self.assertFalse(race.has_no_stealth)
        self.assertFalse(race.has_no_terraforming)
        self.assertFalse(race.only_basic_terraforming)
        transdimensional = ServerRaceType.objects.get(code='TRDM')
        self.assertTrue(transdimensional.has_no_terraforming)
        self.assertFalse(transdimensional.only_basic_terraforming)
        mechanical = ServerRaceType.objects.get(code='MECH')
        self.assertTrue(mechanical.only_basic_terraforming)
        breeders = ServerRaceType.objects.get(code='BRED')
        self.assertTrue(breeders.only_basic_terraforming)

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
        kinetic_impactor = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000220'
        )
        self.assertEqual(kinetic_impactor.category.code, 'MATERIALS')
        self.assertEqual(kinetic_impactor.level, 0)
        self.assertEqual(
            json.loads(kinetic_impactor.params_json).get('offense_level'),
            0.10,
        )
        remote_guided_missile = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000222'
        )
        self.assertEqual(remote_guided_missile.category.code, 'ELECTRONICS')
        self.assertEqual(remote_guided_missile.level, 4)
        self.assertEqual(
            json.loads(remote_guided_missile.params_json).get('offense_level'),
            0.50,
        )
        maelstrom_torpedo = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000226'
        )
        self.assertEqual(maelstrom_torpedo.category.code, 'MATERIALS')
        self.assertEqual(maelstrom_torpedo.level, 26)
        self.assertEqual(
            json.loads(maelstrom_torpedo.params_json).get('offense_level'),
            6.40,
        )
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
        supernova_bombs = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000606'
        )
        self.assertEqual(supernova_bombs.level, 26)
        self.assertEqual(
            json.loads(supernova_bombs.params_json).get('defense_level'), -1.5
        )
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
        terraform_ii = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000408'
        )
        terraform_ii_params = json.loads(terraform_ii.params_json)
        self.assertEqual(
            terraform_ii_params.get('race_type'),
            'has only_basic_terraforming == False',
        )
        self.assertEqual(
            terraform_ii_params['production_cost_overrides']['TERRAFORM_GRAVITY']['bp'],
            100,
        )
        terraform_iii = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000409'
        )
        self.assertEqual(
            json.loads(terraform_iii.params_json).get('race_type'),
            'has only_basic_terraforming == False',
        )
        terraform_iv = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000410'
        )
        self.assertEqual(
            json.loads(terraform_iv.params_json).get('race_type'),
            'has only_basic_terraforming == False',
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
        city_hull = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000507'
        )
        self.assertEqual(
            json.loads(city_hull.params_json).get('race_type'),
            'has has_advanced_hulls',
        )
        self.assertFalse(
            Technology.objects.filter(
                tech_type='HULL',
                hull_design__isnull=True,
            ).exists()
        )
        self.assertIsNotNone(city_hull.hull_design)
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

    def test_sync_applies_race_creation_points_balances_for_default_race_types(self):
        sync_factory_defaults(force=True)

        self.assertEqual(
            ServerRaceType.objects.get(code='SCI').race_creation_points_balance,
            6.0,
        )
        self.assertEqual(
            ServerRaceType.objects.get(code='MECH').race_creation_points_balance,
            12.0,
        )
        self.assertEqual(
            ServerRaceType.objects.get(code='EXPL').race_creation_points_balance,
            10.0,
        )
        self.assertEqual(
            ServerRaceType.objects.get(code='BULD').race_creation_points_balance,
            5.0,
        )
        self.assertEqual(
            ServerRaceType.objects.get(code='BRED').race_creation_points_balance,
            10.0,
        )
        self.assertTrue(ServerRaceType.objects.get(code='BRED').has_no_stealth)
        self.assertTrue(ServerRaceType.objects.get(code='TRAD').has_no_stealth)
        self.assertTrue(ServerRaceType.objects.get(code='BULD').has_no_stealth)
        self.assertTrue(ServerRaceType.objects.get(code='WAR').has_no_stealth)
        self.assertFalse(ServerRaceType.objects.get(code='SCI').has_no_stealth)
        self.assertFalse(ServerRaceType.objects.get(code='MECH').has_no_stealth)
        self.assertFalse(ServerRaceType.objects.get(code='EXPL').has_no_stealth)
        self.assertFalse(ServerRaceType.objects.get(code='PARA').has_no_stealth)

    def test_sync_adds_special_cloak_technologies(self):
        sync_factory_defaults(force=True)

        mini_cloak = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000801'
        )
        self.assertEqual(mini_cloak.tech_type, 'SPECIAL')
        self.assertEqual(mini_cloak.category.code, 'MATERIALS')
        self.assertEqual(mini_cloak.level, 3)
        self.assertEqual(
            json.loads(mini_cloak.params_json),
            {
                'max_cloaked_warp': 3,
                'advanced_cloak': False,
                'defense_level': -0.5,
                'race_type': 'is SCI, is WAR',
            },
        )

        chameleon_cloak = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000802'
        )
        self.assertEqual(json.loads(chameleon_cloak.params_json).get('race_type'), 'WAR')

        prototype_cloak = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000806'
        )
        self.assertEqual(
            json.loads(prototype_cloak.params_json).get('race_type'),
            'has has_no_stealth == False, and is not WAR, and is not SCI',
        )

        advanced_cloak = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000808'
        )
        self.assertEqual(advanced_cloak.category.code, 'CONSTRUCTION')
        self.assertEqual(advanced_cloak.level, 26)
        advanced_params = json.loads(advanced_cloak.params_json)
        self.assertTrue(advanced_params.get('advanced_cloak'))
        self.assertEqual(advanced_params.get('defense_level'), -1.8)

        tactical_cloak = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000804'
        )
        self.assertEqual(
            json.loads(tactical_cloak.params_json).get('defense_level'),
            -1.2,
        )

        super_cloak = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000805'
        )
        self.assertEqual(
            json.loads(super_cloak.params_json).get('defense_level'),
            -0.8,
        )

        standard_cloak = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000807'
        )
        self.assertEqual(
            json.loads(standard_cloak.params_json).get('defense_level'),
            -2.8,
        )

    def test_sync_adds_fuel_factory_technologies(self):
        sync_factory_defaults(force=True)

        fuel_factory = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000809'
        )
        self.assertEqual(fuel_factory.tech_type, 'ELECTRICAL')
        self.assertEqual(fuel_factory.category.code, 'ENERGY')
        self.assertEqual(fuel_factory.level, 18)
        self.assertEqual(
            json.loads(fuel_factory.params_json),
            {
                'fuel_factory_mg_per_year': 1.0,
                'fuel_factory_max_warp': 0,
            },
        )

        advanced_fuel_factory = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000810'
        )
        self.assertEqual(advanced_fuel_factory.category.code, 'ENERGY')
        self.assertEqual(advanced_fuel_factory.level, 22)
        self.assertEqual(
            json.loads(advanced_fuel_factory.params_json),
            {
                'fuel_factory_mg_per_year': 1.0,
                'fuel_factory_max_warp': 5,
            },
        )

        super_fuel_factory = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000811'
        )
        self.assertEqual(super_fuel_factory.category.code, 'ENERGY')
        self.assertEqual(super_fuel_factory.level, 25)
        self.assertEqual(
            json.loads(super_fuel_factory.params_json),
            {
                'fuel_factory_mg_per_year': 2.0,
                'fuel_factory_max_warp': 6,
            },
        )

        supermax_fuel_factory = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000812'
        )
        self.assertEqual(supermax_fuel_factory.category.code, 'ENERGY')
        self.assertEqual(supermax_fuel_factory.level, 26)
        self.assertEqual(
            json.loads(supermax_fuel_factory.params_json),
            {
                'fuel_factory_mg_per_year': 2.0,
                'fuel_factory_max_warp': 8,
            },
        )

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

    def test_sync_defaults_command_restores_race_type_and_technology_defaults(self):
        sync_factory_defaults(force=True)

        race = ServerRaceType.objects.get(code='WAR')
        technology = Technology.objects.get(
            id='00000000-0000-0000-0000-000000000604'
        )
        race.has_no_stealth = False
        race.save(update_fields=['has_no_stealth'])
        technology.level = 99
        technology.save(update_fields=['level'])

        stdout = StringIO()
        call_command('sync_defaults', stdout=stdout)

        race.refresh_from_db()
        technology.refresh_from_db()
        self.assertTrue(race.has_no_stealth)
        self.assertEqual(technology.level, 12)
        self.assertIn('Synced fixture-backed defaults', stdout.getvalue())

    def test_sync_tech_tree_command_refreshes_server_race_type_defaults_too(self):
        sync_factory_defaults(force=True)

        race = ServerRaceType.objects.get(code='JOAT')
        race.name = 'Drifted JOAT'
        race.save(update_fields=['name'])

        stdout = StringIO()
        call_command('sync_tech_tree', stdout=stdout)

        race.refresh_from_db()
        self.assertEqual(race.name, 'Jack of All Trades')
        self.assertIn('Synced fixture-backed defaults', stdout.getvalue())
