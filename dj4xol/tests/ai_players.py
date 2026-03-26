from django.test import TestCase
from unittest.mock import patch

from ..ai_players import (
    AI_MODULE_OPENAI,
    AI_SLOT_RANDOM_STANCE,
    build_random_ai_race_template,
    ai_module_choices,
    apply_ai_module_turn,
    is_ai_module_enabled,
    resolve_ai_slot_stance,
)
from ..factory import GameFactory
from ..models import ServerSettings
from ..habitability_rules import RaceCreationRules
from ._util import default_game, get_default_race


class TestAIPlayerModules(TestCase):
    def _set_server_setting(self, key, value, description):
        ServerSettings.objects.update_or_create(
            key=key,
            defaults={
                'value': value,
                'long_value': value,
                'description': description,
            },
        )

    def test_ai_module_choices_include_openai_module(self):
        codes = [code for code, _label in ai_module_choices(enabled_only=False)]
        self.assertIn(AI_MODULE_OPENAI, codes)

    def test_openai_module_disabled_by_default(self):
        self.assertFalse(is_ai_module_enabled(AI_MODULE_OPENAI))

    def test_openai_module_turn_respects_iteration_quota(self):
        game = default_game(stars=8)
        ai_player = GameFactory(game).join_player(
            None,
            get_default_race(),
            invited=True,
            is_ai=True,
            ai_module=AI_MODULE_OPENAI,
        )
        self.assertIsNotNone(ai_player)

        self._set_server_setting(
            'ai_module_openai_enabled',
            'True',
            'Enable AI module: openai',
        )
        self._set_server_setting(
            'ai_module_openai_config',
            '{"api_key":"test-key","model":"test-model","max_iterations":2}',
            'AI module config: openai',
        )

        with patch(
            'dj4xol.ai_players._openai_chat_completion',
            side_effect=[
                '{"command":"/status","done":false}',
                '{"done":true}',
            ],
        ):
            result = apply_ai_module_turn(ai_player, game)

        self.assertTrue(result.get('ok'))
        self.assertEqual(result.get('iterations_used'), 2)
        self.assertEqual(result.get('commands_executed'), 1)

    def test_random_ai_stance_never_returns_allied(self):
        for _idx in range(40):
            stance = resolve_ai_slot_stance(AI_SLOT_RANDOM_STANCE)
            self.assertIn(stance, {'HOSTILE', 'COLD', 'NEUTRAL', 'WARM'})
            self.assertNotEqual(stance, 'ALLIED')

    def test_random_ai_race_respects_budget_and_race_overrides(self):
        race = build_random_ai_race_template(max_starting_tech_level=5)
        race_type = race.race_type
        self.assertIsNotNone(race_type)
        rules = RaceCreationRules(
            centers={
                'gravity': race.gravity_center,
                'temperature': race.temperature_center,
                'radiation': race.radiation_center,
            },
            widths={
                'gravity': race.gravity_width,
                'temperature': race.temperature_width,
                'radiation': race.radiation_width,
            },
            starting_colonists=race.starting_colonists,
            starting_mines=race.starting_mines,
            starting_factories=race.starting_factories,
            starting_labs=race.starting_labs,
            starting_shipyards=race.starting_shipyards,
            starting_fleets=race.starting_fleets,
            starting_tech_level=race.starting_tech_level,
            race_type_points_balance=float(
                getattr(race_type, 'race_creation_points_balance', 0.0) or 0.0
            ),
        )
        self.assertLessEqual(rules.total_cost(), rules.budget)
        self.assertFalse(rules.validate())
        if bool(getattr(race_type, 'ignores_gravity', False)):
            self.assertEqual(float(race.gravity_center), 1.0)
            self.assertEqual(float(race.gravity_width), 1.0)
        if bool(getattr(race_type, 'ignores_temperature', False)):
            self.assertEqual(float(race.temperature_center), 1.0)
            self.assertEqual(float(race.temperature_width), 1.0)
        if bool(getattr(race_type, 'ignores_radiation', False)):
            self.assertEqual(float(race.radiation_center), 1.0)
            self.assertEqual(float(race.radiation_width), 1.0)
