from django.test import Client, TestCase
from django.urls import reverse

from ..models import PlayerResearch, ResearchCategory
from ._util import default_game, get_default_user


class ResearchViewTest(TestCase):
    def setUp(self):
        self.game = default_game(stars=5)
        self.player = self.game.players.first()
        self.user, _ = get_default_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.energy = ResearchCategory.objects.create(
            code='ENERGY', name='Energy', display_order=10, enabled=True
        )
        self.electronics = ResearchCategory.objects.create(
            code='ELECT', name='Electronics', display_order=20, enabled=True
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
        self.assertEqual(response.status_code, 200)
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
        self.assertEqual(response.status_code, 200)
        rows = {
            row.category_id: row.allocation_percent
            for row in PlayerResearch.objects.filter(player=self.player)
        }
        self.assertEqual(rows[self.electronics.id], 100.0)
        self.assertEqual(rows[self.energy.id], 0.0)

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
