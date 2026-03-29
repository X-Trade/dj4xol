from django.test import TestCase

from ..models import ServerRaceType
from ..technology_gate_rules import (
    describe_race_type_requirement,
    parse_race_type_requirement,
    race_type_requirement_matches,
    race_type_requirement_viewer_status,
)


class TechnologyGateRulesTest(TestCase):
    def setUp(self):
        self.stealth_race = ServerRaceType.objects.create(
            code='STLH',
            name='Stealth Race',
            description='Test race',
            has_no_stealth=False,
            has_advanced_hulls=True,
            economy_offset=2,
        )
        self.basic_race = ServerRaceType.objects.create(
            code='BASC',
            name='Basic Race',
            description='Test race',
            has_no_stealth=True,
            has_advanced_hulls=False,
            economy_offset=0,
        )

    def test_parse_supported_requirement_forms(self):
        self.assertEqual(
            parse_race_type_requirement('SCI'),
            {'kind': 'code', 'code': 'SCI', 'negate': False},
        )
        self.assertEqual(
            parse_race_type_requirement('not WAR'),
            {'kind': 'code', 'code': 'WAR', 'negate': True},
        )
        self.assertEqual(
            parse_race_type_requirement('has has_no_stealth'),
            {'kind': 'has', 'field': 'has_no_stealth'},
        )
        self.assertEqual(
            parse_race_type_requirement('has has_no_stealth == False'),
            {
                'kind': 'compare',
                'field': 'has_no_stealth',
                'operator': '==',
                'raw_value': 'False',
                'value': False,
            },
        )
        self.assertEqual(
            parse_race_type_requirement('has economy_offset >= 1'),
            {
                'kind': 'compare',
                'field': 'economy_offset',
                'operator': '>=',
                'raw_value': '1',
                'value': 1,
            },
        )

    def test_matches_supported_requirement_forms(self):
        self.assertTrue(race_type_requirement_matches('STLH', self.stealth_race))
        self.assertFalse(race_type_requirement_matches('STLH', self.basic_race))
        self.assertTrue(race_type_requirement_matches('not STLH', self.basic_race))
        self.assertFalse(race_type_requirement_matches('not STLH', self.stealth_race))
        self.assertTrue(race_type_requirement_matches('has has_no_stealth', self.basic_race))
        self.assertFalse(race_type_requirement_matches('has has_no_stealth', self.stealth_race))
        self.assertTrue(
            race_type_requirement_matches('has has_no_stealth == False', self.stealth_race)
        )
        self.assertFalse(
            race_type_requirement_matches('has has_no_stealth == False', self.basic_race)
        )
        self.assertTrue(
            race_type_requirement_matches('has economy_offset >= 1', self.stealth_race)
        )
        self.assertFalse(
            race_type_requirement_matches('has economy_offset >= 1', self.basic_race)
        )
        self.assertTrue(
            race_type_requirement_matches(['SCI', 'STLH'], self.stealth_race)
        )
        self.assertFalse(
            race_type_requirement_matches(['SCI', 'WAR'], self.basic_race)
        )
        self.assertTrue(
            race_type_requirement_matches('is STLH, is SCI', self.stealth_race)
        )
        self.assertFalse(
            race_type_requirement_matches('is SCI, is WAR', self.basic_race)
        )
        self.assertTrue(
            race_type_requirement_matches(
                'is STLH, and has has_advanced_hulls',
                self.stealth_race,
            )
        )
        self.assertFalse(
            race_type_requirement_matches(
                'is BASC, and has has_advanced_hulls',
                self.basic_race,
            )
        )

    def test_viewer_status_matches_supported_requirement_forms(self):
        self.assertEqual(
            race_type_requirement_viewer_status('STLH', self.stealth_race),
            'included',
        )
        self.assertIsNone(race_type_requirement_viewer_status('STLH', self.basic_race))
        self.assertEqual(
            race_type_requirement_viewer_status('not STLH', self.stealth_race),
            'excluded',
        )
        self.assertIsNone(
            race_type_requirement_viewer_status('not STLH', self.basic_race)
        )
        self.assertEqual(
            race_type_requirement_viewer_status('has has_no_stealth', self.basic_race),
            'included',
        )
        self.assertIsNone(
            race_type_requirement_viewer_status('has has_no_stealth', self.stealth_race)
        )
        self.assertIsNone(
            race_type_requirement_viewer_status(
                'has has_no_stealth == False',
                self.stealth_race,
            )
        )
        self.assertEqual(
            race_type_requirement_viewer_status(
                'has has_no_stealth == False',
                self.basic_race,
            ),
            'excluded',
        )
        self.assertEqual(
            race_type_requirement_viewer_status(['SCI', 'STLH'], self.stealth_race),
            'included',
        )
        self.assertEqual(
            race_type_requirement_viewer_status(['not BASC', 'not STLH'], self.basic_race),
            'excluded',
        )
        self.assertIsNone(
            race_type_requirement_viewer_status(['SCI', 'WAR'], self.basic_race)
        )
        self.assertEqual(
            race_type_requirement_viewer_status('is STLH, is SCI', self.stealth_race),
            'included',
        )
        self.assertEqual(
            race_type_requirement_viewer_status('not BASC, is SCI', self.basic_race),
            'excluded',
        )

    def test_describe_humanises_requirement_forms(self):
        self.assertEqual(describe_race_type_requirement('not WAR'), 'Is not WAR')
        self.assertEqual(
            describe_race_type_requirement('has has_advanced_hulls'),
            'Has advanced hulls',
        )
        self.assertEqual(
            describe_race_type_requirement('has has_no_stealth == False'),
            'Has no stealth systems is False',
        )
        self.assertEqual(
            describe_race_type_requirement('has has_no_stealth != False'),
            'Has no stealth systems is not False',
        )
        self.assertEqual(
            describe_race_type_requirement(['SCI', 'WAR']),
            'Is SCI or Is WAR',
        )
        self.assertEqual(
            describe_race_type_requirement('is SCI, is WAR'),
            'Is SCI or Is WAR',
        )
        self.assertEqual(
            describe_race_type_requirement('is SCI, and is WAR'),
            'Is SCI and Is WAR',
        )
