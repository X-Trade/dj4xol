from django.test import TestCase
from unittest.mock import patch

from ..ai_players import (
    AI_MODULE_MICROMANAGER,
    AI_MODULE_OPENAI,
    AI_MODULE_IDLE,
    AI_SLOT_RANDOM_STANCE,
    build_random_ai_race_template,
    ai_module_choices,
    apply_ai_module_turn,
    count_active_ai_players,
    get_remaining_server_ai_capacity,
    is_ai_module_enabled,
    resolve_ai_slot_stance,
)
from ..factory import GameFactory
from ..models import (
    DiplomaticContract,
    PlayerDiplomaticStance,
    PlayerTechnologyGrant,
    ResearchCategory,
    ServerSettings,
    Technology,
)
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

    def test_idle_ai_rejects_non_material_stance_request(self):
        game = default_game(stars=8)
        sender = game.players.first()
        ai_player = GameFactory(game).join_player(
            None,
            get_default_race(),
            invited=True,
            is_ai=True,
            ai_module=AI_MODULE_IDLE,
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=sender,
            recipient=ai_player,
            status=DiplomaticContract.STATUS_SENT,
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type=DiplomaticContract.CLAUSE_STANCE,
            request_stance='WARM',
            offer_clause_type=DiplomaticContract.CLAUSE_NOTHING,
        )

        with patch('dj4xol.ai_players.random.random', return_value=0.99):
            apply_ai_module_turn(ai_player, game)

        contract.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_DECLINED)

    def test_repeated_idle_ai_rejections_downgrade_stance(self):
        game = default_game(stars=8)
        sender = game.players.first()
        ai_player = GameFactory(game).join_player(
            None,
            get_default_race(),
            invited=True,
            is_ai=True,
            ai_module=AI_MODULE_IDLE,
        )

        for _idx in range(2):
            DiplomaticContract.objects.create(
                game=game,
                sender=sender,
                recipient=ai_player,
                status=DiplomaticContract.STATUS_SENT,
                sent_year=game.year,
                expires_year=game.year + 24,
                request_clause_type=DiplomaticContract.CLAUSE_STANCE,
                request_stance='WARM',
                offer_clause_type=DiplomaticContract.CLAUSE_NOTHING,
            )
            with patch('dj4xol.ai_players.random.random', return_value=0.99):
                apply_ai_module_turn(ai_player, game)

        stance_row = PlayerDiplomaticStance.objects.get(
            player=ai_player,
            target_player=sender,
        )
        self.assertEqual(stance_row.pending_stance, 'COLD')

    def test_idle_ai_accepts_material_offer_of_specific_fleet(self):
        game = default_game(stars=8)
        sender = game.players.first()
        ai_player = GameFactory(game).join_player(
            None,
            get_default_race(),
            invited=True,
            is_ai=True,
            ai_module=AI_MODULE_IDLE,
        )
        offered_fleet = sender.fleets.first()
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=sender,
            recipient=ai_player,
            status=DiplomaticContract.STATUS_SENT,
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type=DiplomaticContract.CLAUSE_NOTHING,
            offer_clause_type=DiplomaticContract.CLAUSE_SPECIFIC_FLEET,
            offer_fleet=offered_fleet,
        )

        apply_ai_module_turn(ai_player, game)

        contract.refresh_from_db()
        offered_fleet.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_FULFILLED)
        self.assertEqual(offered_fleet.player_id, ai_player.id)

    def test_passive_ai_rejects_unimplemented_delivery_requests(self):
        game = default_game(stars=8)
        sender = game.players.first()
        offered_fleet = sender.fleets.first()
        for module_code in (AI_MODULE_IDLE, AI_MODULE_MICROMANAGER):
            ai_player = GameFactory(game).join_player(
                None,
                get_default_race(),
                invited=True,
                is_ai=True,
                ai_module=module_code,
            )
            contract = DiplomaticContract.objects.create(
                game=game,
                sender=sender,
                recipient=ai_player,
                status=DiplomaticContract.STATUS_SENT,
                sent_year=game.year,
                expires_year=game.year + 24,
                request_clause_type=DiplomaticContract.CLAUSE_RESOURCE_TO_WORLD,
                request_ironium=250,
                offer_clause_type=DiplomaticContract.CLAUSE_SPECIFIC_FLEET,
                offer_fleet=offered_fleet,
            )
            apply_ai_module_turn(ai_player, game)
            contract.refresh_from_db()
            self.assertEqual(contract.status, DiplomaticContract.STATUS_DECLINED)

    def test_micromanager_ai_rejects_homeworld_transfer_request(self):
        game = default_game(stars=8)
        sender = game.players.first()
        ai_player = GameFactory(game).join_player(
            None,
            get_default_race(),
            invited=True,
            is_ai=True,
            ai_module=AI_MODULE_MICROMANAGER,
        )
        offered_fleet = sender.fleets.first()
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=sender,
            recipient=ai_player,
            status=DiplomaticContract.STATUS_SENT,
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type=DiplomaticContract.CLAUSE_SPECIFIC_COLONY,
            request_star=ai_player.homeworld,
            offer_clause_type=DiplomaticContract.CLAUSE_SPECIFIC_FLEET,
            offer_fleet=offered_fleet,
        )

        apply_ai_module_turn(ai_player, game)

        contract.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_DECLINED)

    def test_micromanager_technology_trade_requires_new_offered_technology(self):
        game = default_game(stars=8)
        sender = game.players.first()
        ai_player = GameFactory(game).join_player(
            None,
            get_default_race(),
            invited=True,
            is_ai=True,
            ai_module=AI_MODULE_MICROMANAGER,
        )
        category, _created = ResearchCategory.objects.get_or_create(
            code='AI_DIP',
            defaults={'name': 'AI Diplomacy', 'enabled': True, 'display_order': 500},
        )
        request_tech = Technology.objects.create(
            category=category,
            level=1,
            name='AI Requested Tech',
            tech_type='ELECTRONICS',
            enabled=True,
            params_json='{}',
        )
        offer_tech = Technology.objects.create(
            category=category,
            level=1,
            name='AI Offered Tech',
            tech_type='ELECTRONICS',
            enabled=True,
            params_json='{}',
        )
        PlayerTechnologyGrant.objects.create(player=ai_player, technology=request_tech)
        PlayerTechnologyGrant.objects.create(player=sender, technology=offer_tech)
        PlayerTechnologyGrant.objects.create(player=ai_player, technology=offer_tech)
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=sender,
            recipient=ai_player,
            status=DiplomaticContract.STATUS_SENT,
            sent_year=game.year,
            expires_year=game.year + 24,
            request_clause_type=DiplomaticContract.CLAUSE_TECHNOLOGY,
            request_technology=request_tech,
            offer_clause_type=DiplomaticContract.CLAUSE_TECHNOLOGY,
            offer_technology=offer_tech,
        )

        with patch('dj4xol.ai_players.random.random', return_value=0.0):
            apply_ai_module_turn(ai_player, game)

        contract.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_DECLINED)

    def test_micromanager_ai_highly_accepts_pure_fleet_gift(self):
        game = default_game(stars=8)
        sender = game.players.first()
        ai_player = GameFactory(game).join_player(
            None,
            get_default_race(),
            invited=True,
            is_ai=True,
            ai_module=AI_MODULE_MICROMANAGER,
        )
        offered_fleet = sender.fleets.first()
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=sender,
            recipient=ai_player,
            status=DiplomaticContract.STATUS_SENT,
            sent_year=game.year,
            expires_year=game.year + 20,
            request_clause_type=DiplomaticContract.CLAUSE_NOTHING,
            offer_clause_type=DiplomaticContract.CLAUSE_SPECIFIC_FLEET,
            offer_fleet=offered_fleet,
        )

        with patch('dj4xol.ai_players.random.random', return_value=0.50):
            apply_ai_module_turn(ai_player, game)

        contract.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_FULFILLED)

    def test_micromanager_ai_tech_gift_higher_level_more_likely(self):
        game = default_game(stars=8)
        sender = game.players.first()
        ai_player = GameFactory(game).join_player(
            None,
            get_default_race(),
            invited=True,
            is_ai=True,
            ai_module=AI_MODULE_MICROMANAGER,
        )
        category, _created = ResearchCategory.objects.get_or_create(
            code='AI_GIFT',
            defaults={'name': 'AI Gift', 'enabled': True, 'display_order': 510},
        )
        baseline = Technology.objects.create(
            category=category,
            level=2,
            name='Gift Baseline',
            tech_type='ELECTRONICS',
            enabled=True,
            params_json='{}',
        )
        low_offer = Technology.objects.create(
            category=category,
            level=3,
            name='Gift Low',
            tech_type='ELECTRONICS',
            enabled=True,
            params_json='{}',
        )
        high_offer = Technology.objects.create(
            category=category,
            level=6,
            name='Gift High',
            tech_type='ELECTRONICS',
            enabled=True,
            params_json='{}',
        )
        PlayerTechnologyGrant.objects.create(player=ai_player, technology=baseline)
        PlayerTechnologyGrant.objects.create(player=sender, technology=low_offer)
        PlayerTechnologyGrant.objects.create(player=sender, technology=high_offer)

        low_contract = DiplomaticContract.objects.create(
            game=game,
            sender=sender,
            recipient=ai_player,
            status=DiplomaticContract.STATUS_SENT,
            sent_year=game.year,
            expires_year=game.year + 20,
            request_clause_type=DiplomaticContract.CLAUSE_NOTHING,
            offer_clause_type=DiplomaticContract.CLAUSE_TECHNOLOGY,
            offer_technology=low_offer,
        )
        with patch('dj4xol.ai_players.random.random', return_value=0.82):
            apply_ai_module_turn(ai_player, game)
        low_contract.refresh_from_db()
        self.assertEqual(low_contract.status, DiplomaticContract.STATUS_DECLINED)

        high_contract = DiplomaticContract.objects.create(
            game=game,
            sender=sender,
            recipient=ai_player,
            status=DiplomaticContract.STATUS_SENT,
            sent_year=game.year,
            expires_year=game.year + 20,
            request_clause_type=DiplomaticContract.CLAUSE_NOTHING,
            offer_clause_type=DiplomaticContract.CLAUSE_TECHNOLOGY,
            offer_technology=high_offer,
        )
        with patch('dj4xol.ai_players.random.random', return_value=0.60):
            apply_ai_module_turn(ai_player, game)
        high_contract.refresh_from_db()
        self.assertEqual(high_contract.status, DiplomaticContract.STATUS_FULFILLED)

    def test_micromanager_ai_habitable_colony_gift_uses_high_acceptance(self):
        game = default_game(stars=10)
        sender = game.players.first()
        ai_player = GameFactory(game).join_player(
            None,
            get_default_race(),
            invited=True,
            is_ai=True,
            ai_module=AI_MODULE_MICROMANAGER,
        )
        gift_colony = game.stars.filter(player__isnull=True).exclude(
            id=sender.homeworld_id
        ).first()
        self.assertIsNotNone(gift_colony)
        gift_colony.player = sender
        gift_colony.colonists = 25000
        gift_colony.gravity = ai_player.gravity_center
        gift_colony.temperature = ai_player.temperature_center
        gift_colony.radiation = ai_player.radiation_center
        gift_colony.save(update_fields=[
            'player', 'colonists', 'gravity', 'temperature', 'radiation',
        ])
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=sender,
            recipient=ai_player,
            status=DiplomaticContract.STATUS_SENT,
            sent_year=game.year,
            expires_year=game.year + 20,
            request_clause_type=DiplomaticContract.CLAUSE_NOTHING,
            offer_clause_type=DiplomaticContract.CLAUSE_SPECIFIC_COLONY,
            offer_star=gift_colony,
        )

        with patch('dj4xol.ai_players.random.random', return_value=0.61):
            apply_ai_module_turn(ai_player, game)

        contract.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_FULFILLED)

    def test_micromanager_ai_multiple_accepted_gifts_raise_stance(self):
        game = default_game(stars=10)
        sender = game.players.first()
        ai_player = GameFactory(game).join_player(
            None,
            get_default_race(),
            invited=True,
            is_ai=True,
            ai_module=AI_MODULE_MICROMANAGER,
        )

        for _idx in range(2):
            offered_fleet = sender.fleets.first()
            contract = DiplomaticContract.objects.create(
                game=game,
                sender=sender,
                recipient=ai_player,
                status=DiplomaticContract.STATUS_SENT,
                sent_year=game.year,
                expires_year=game.year + 20,
                request_clause_type=DiplomaticContract.CLAUSE_NOTHING,
                offer_clause_type=DiplomaticContract.CLAUSE_SPECIFIC_FLEET,
                offer_fleet=offered_fleet,
            )
            with patch('dj4xol.ai_players.random.random', return_value=0.10):
                apply_ai_module_turn(ai_player, game)
            contract.refresh_from_db()
            self.assertEqual(contract.status, DiplomaticContract.STATUS_FULFILLED)

        stance_row = PlayerDiplomaticStance.objects.get(
            player=ai_player,
            target_player=sender,
        )
        self.assertEqual(stance_row.pending_stance, 'WARM')

    def test_micromanager_ai_stance_for_stance_lower_is_more_likely(self):
        game = default_game(stars=8)
        sender = game.players.first()
        ai_player = GameFactory(game).join_player(
            None,
            get_default_race(),
            invited=True,
            is_ai=True,
            ai_module=AI_MODULE_MICROMANAGER,
        )
        PlayerDiplomaticStance.objects.create(
            player=ai_player,
            target_player=sender,
            stance='WARM',
            pending_stance='WARM',
        )
        contract = DiplomaticContract.objects.create(
            game=game,
            sender=sender,
            recipient=ai_player,
            status=DiplomaticContract.STATUS_SENT,
            sent_year=game.year,
            expires_year=game.year + 20,
            request_clause_type=DiplomaticContract.CLAUSE_STANCE,
            request_stance='COLD',
            offer_clause_type=DiplomaticContract.CLAUSE_STANCE,
            offer_stance='NEUTRAL',
        )

        with patch('dj4xol.ai_players.random.random', return_value=0.50):
            apply_ai_module_turn(ai_player, game)

        contract.refresh_from_db()
        self.assertEqual(contract.status, DiplomaticContract.STATUS_FULFILLED)

    def test_micromanager_ai_stance_raise_by_one_uses_success_history_weighting(self):
        game = default_game(stars=8)
        sender = game.players.first()
        ai_player = GameFactory(game).join_player(
            None,
            get_default_race(),
            invited=True,
            is_ai=True,
            ai_module=AI_MODULE_MICROMANAGER,
        )
        PlayerDiplomaticStance.objects.create(
            player=ai_player,
            target_player=sender,
            stance='NEUTRAL',
            pending_stance='NEUTRAL',
        )

        first_raise = DiplomaticContract.objects.create(
            game=game,
            sender=sender,
            recipient=ai_player,
            status=DiplomaticContract.STATUS_SENT,
            sent_year=game.year,
            expires_year=game.year + 20,
            request_clause_type=DiplomaticContract.CLAUSE_STANCE,
            request_stance='WARM',
            offer_clause_type=DiplomaticContract.CLAUSE_STANCE,
            offer_stance='NEUTRAL',
        )
        with patch('dj4xol.ai_players.random.random', return_value=0.24):
            apply_ai_module_turn(ai_player, game)
        first_raise.refresh_from_db()
        self.assertEqual(first_raise.status, DiplomaticContract.STATUS_DECLINED)

        for year in (game.year, game.year - 10):
            DiplomaticContract.objects.create(
                game=game,
                sender=sender,
                recipient=ai_player,
                status=DiplomaticContract.STATUS_FULFILLED,
                sent_year=year,
                expires_year=year + 10,
                accepted_year=year,
                handled_year=year,
                fulfilled_year=year,
                request_clause_type=DiplomaticContract.CLAUSE_NOTHING,
                offer_clause_type=DiplomaticContract.CLAUSE_NOTHING,
            )

        second_raise = DiplomaticContract.objects.create(
            game=game,
            sender=sender,
            recipient=ai_player,
            status=DiplomaticContract.STATUS_SENT,
            sent_year=game.year,
            expires_year=game.year + 20,
            request_clause_type=DiplomaticContract.CLAUSE_STANCE,
            request_stance='WARM',
            offer_clause_type=DiplomaticContract.CLAUSE_STANCE,
            offer_stance='NEUTRAL',
        )
        with patch('dj4xol.ai_players.random.random', return_value=0.24):
            apply_ai_module_turn(ai_player, game)
        second_raise.refresh_from_db()
        self.assertEqual(second_raise.status, DiplomaticContract.STATUS_FULFILLED)

    def test_server_cap_count_excludes_idle_and_micromanager(self):
        game = default_game(stars=8)
        race = get_default_race()
        factory = GameFactory(game)
        factory.join_player(None, race, invited=True, is_ai=True, ai_module=AI_MODULE_IDLE)
        factory.join_player(None, race, invited=True, is_ai=True, ai_module=AI_MODULE_MICROMANAGER)
        factory.join_player(None, race, invited=True, is_ai=True, ai_module=AI_MODULE_OPENAI)
        self._set_server_setting(
            'ai_max_per_server',
            '2',
            'Maximum active AI players per server',
        )

        self.assertEqual(count_active_ai_players(server_capped_only=False), 3)
        self.assertEqual(count_active_ai_players(server_capped_only=True), 1)
        self.assertEqual(get_remaining_server_ai_capacity(), 1)
