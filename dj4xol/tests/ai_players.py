from django.test import TestCase
from unittest.mock import patch

from ..ai_players import (
    AI_MODULE_OPENAI,
    ai_module_choices,
    apply_ai_module_turn,
    is_ai_module_enabled,
)
from ..factory import GameFactory
from ..models import ServerSettings
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
