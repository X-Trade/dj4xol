from django.test import Client, TestCase
from django.urls import reverse

from ..models import ResearchCategory, Technology
from ._util import get_default_user


class HelpPagesTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user, _ = get_default_user()
        self.client.force_login(self.user)

    def test_help_index_renders(self):
        response = self.client.get(reverse('dj4xol:help_index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Help Index')
        self.assertContains(response, 'Colony Calculator')
        self.assertContains(response, 'Technology Directory')
        self.assertContains(response, 'Space Combat')
        self.assertContains(response, 'Invasion')

    def test_help_space_combat_renders(self):
        response = self.client.get(reverse('dj4xol:help_space_combat'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Space Combat')
        self.assertContains(response, 'Damage Resolution')

    def test_help_invasion_renders(self):
        response = self.client.get(reverse('dj4xol:help_invasion'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invasion')
        self.assertContains(response, 'Stage 1: Planetary Defence Fire')

    def test_help_technology_renders_and_filters(self):
        energy = ResearchCategory.objects.create(
            code='ENERHELP',
            name='Energy',
            display_order=10,
            enabled=True,
        )
        materials = ResearchCategory.objects.create(
            code='MATHELP',
            name='Materials',
            display_order=20,
            enabled=True,
        )
        Technology.objects.create(
            category=energy,
            level=2,
            name='Laser Test',
            tech_type='ENERGY_WEAPON',
            params_json='{"offense_level": 1.2}',
            enabled=True,
        )
        Technology.objects.create(
            category=materials,
            level=4,
            name='Shield Test',
            tech_type='SHIELD',
            params_json='{"defense_level": 2.0}',
            enabled=True,
        )

        response = self.client.get(reverse('dj4xol:help_technology'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Technology Directory')
        self.assertContains(response, 'Search')
        self.assertContains(response, 'Categories')
        self.assertContains(response, 'Search')
        self.assertContains(response, 'Laser Test')
        self.assertContains(response, 'Shield Test')

        response = self.client.get(reverse('dj4xol:help_technology'), {
            'category': str(energy.id),
            'max_level': '2',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Laser Test')
        self.assertNotContains(response, 'Shield Test')
