from django.test import Client, TestCase
from django.urls import reverse

from ..models import PlayerResearch, ResearchCategory, Technology
from ..research import ensure_player_research_rows
from ._util import default_game, get_default_user


class ResearchViewTest(TestCase):
    def setUp(self):
        self.game = default_game(stars=5)
        self.player = self.game.players.first()
        self.user, _ = get_default_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.energy, _ = ResearchCategory.objects.get_or_create(
            code='VIEW_ENERGY',
            defaults={'name': 'View Energy', 'display_order': 10, 'enabled': True}
        )
        self.electronics, _ = ResearchCategory.objects.get_or_create(
            code='VIEW_ELECT',
            defaults={'name': 'View Electronics', 'display_order': 20, 'enabled': True}
        )

    def test_research_view_renders(self):
        response = self.client.get(
            reverse('dj4xol:research', args=[self.game.short_id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Research Budget')
        self.assertContains(response, 'Allocations')

    def test_research_allocation_normalises_without_error(self):
        response = self.client.post(
            reverse('dj4xol:research', args=[self.game.short_id]),
            {
                'alloc_%s' % self.energy.id: '80',
                'alloc_%s' % self.electronics.id: '80',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse('dj4xol:research', args=[self.game.short_id]),
        )
        rows = PlayerResearch.objects.filter(player=self.player)
        total = sum(row.allocation_percent for row in rows)
        self.assertAlmostEqual(total, 100.0, places=5)

    def test_singular_research_focuses_one_category(self):
        self.player.singular_research = True
        self.player.save(update_fields=['singular_research'])
        response = self.client.post(
            reverse('dj4xol:research', args=[self.game.short_id]),
            {
                'focus_category': str(self.electronics.id),
                'alloc_action': 'focus',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse('dj4xol:research', args=[self.game.short_id]),
        )
        rows = {
            row.category_id: row.allocation_percent
            for row in PlayerResearch.objects.filter(player=self.player)
        }
        self.assertEqual(rows[self.electronics.id], 100.0)
        self.assertEqual(rows[self.energy.id], 0.0)

    def test_singular_research_view_hides_set_focus_button(self):
        self.player.singular_research = True
        self.player.save(update_fields=['singular_research'])
        response = self.client.get(
            reverse('dj4xol:research', args=[self.game.short_id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Set Focus')

    def test_turn_in_from_research_redirects_back_to_research(self):
        response = self.client.post(
            reverse('dj4xol:turn_in', args=[self.game.short_id]),
            {'return_to': 'research'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse('dj4xol:research', args=[self.game.short_id]),
        )

    def test_turn_in_from_research_preserves_selected_category(self):
        response = self.client.post(
            reverse('dj4xol:turn_in', args=[self.game.short_id]),
            {'return_to': 'research', 'category': self.energy.id}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            '%s?category=%s' % (
                reverse('dj4xol:research', args=[self.game.short_id]),
                self.energy.id,
            ),
        )

    def test_research_post_redirects_to_selected_category(self):
        response = self.client.post(
            reverse('dj4xol:research', args=[self.game.short_id]),
            {
                'category': str(self.energy.id),
                'alloc_%s' % self.energy.id: '60',
                'alloc_%s' % self.electronics.id: '40',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            '%s?category=%s' % (
                reverse('dj4xol:research', args=[self.game.short_id]),
                self.energy.id,
            ),
        )

    def test_turned_in_research_view_disables_allocation_controls(self):
        self.player.turned_in = True
        self.player.save(update_fields=['turned_in'])

        response = self.client.get(
            reverse('dj4xol:research', args=[self.game.short_id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="allocation-input"', status_code=200)
        self.assertContains(response, 'class="allocation-control"', status_code=200)
        self.assertContains(response, 'disabled', status_code=200)
        self.assertContains(response, 'id="alloc-even-btn"', status_code=200)
        self.assertContains(response, '?category=', status_code=200)

    def test_research_detail_shows_recently_unlocked_for_current_level(self):
        Technology.objects.create(
            category=self.energy,
            level=1,
            name='Energy Shield I',
            tech_type='SHIELD',
            description='Current shield envelope.',
            params_json='{"shield_level": 1}',
            enabled=True,
        )
        Technology.objects.create(
            category=self.energy,
            level=2,
            name='Energy Shield II',
            tech_type='SHIELD',
            description='Next shield envelope.',
            params_json='{"shield_level": 2}',
            enabled=True,
        )
        ensure_player_research_rows(self.player)
        row = PlayerResearch.objects.get(player=self.player, category=self.energy)
        row.current_level = 1.0
        row.save(update_fields=['current_level'])

        response = self.client.get(
            reverse('dj4xol:research', args=[self.game.short_id]),
            {'category': self.energy.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Recently Unlocked')
        self.assertContains(response, 'Energy Shield I')
        self.assertContains(response, 'Current shield envelope.')
        self.assertContains(response, 'Energy Shield II')

    def test_research_detail_hides_race_gated_technology(self):
        Technology.objects.create(
            category=self.energy,
            level=1,
            name='Open Shield',
            tech_type='SHIELD',
            description='Visible to everyone.',
            params_json='{"shield_level": 1}',
            enabled=True,
        )
        Technology.objects.create(
            category=self.energy,
            level=2,
            name='War Shield',
            tech_type='SHIELD',
            description='Restricted shield.',
            params_json='{"shield_level": 2, "race_type": "is WAR"}',
            enabled=True,
        )
        ensure_player_research_rows(self.player)
        row = PlayerResearch.objects.get(player=self.player, category=self.energy)
        row.current_level = 1.0
        row.save(update_fields=['current_level'])

        response = self.client.get(
            reverse('dj4xol:research', args=[self.game.short_id]),
            {'category': self.energy.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Open Shield')
        self.assertNotContains(response, 'War Shield')

    def test_research_detail_still_advances_when_next_item_is_race_gated(self):
        Technology.objects.create(
            category=self.energy,
            level=1,
            name='Open Shield',
            tech_type='SHIELD',
            description='Visible to everyone.',
            params_json='{"shield_level": 1}',
            enabled=True,
        )
        Technology.objects.create(
            category=self.energy,
            level=2,
            name='War Shield',
            tech_type='SHIELD',
            description='Restricted shield.',
            params_json='{"shield_level": 2, "race_type": "is WAR"}',
            enabled=True,
        )
        ensure_player_research_rows(self.player)
        row = PlayerResearch.objects.get(player=self.player, category=self.energy)
        row.current_level = 1.0
        row.save(update_fields=['current_level'])

        response = self.client.get(
            reverse('dj4xol:research', args=[self.game.short_id]),
            {'category': self.energy.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Next Level')
        self.assertContains(response, 'L2')
        self.assertContains(
            response,
            'No technology items defined for the next level in this category.',
        )
