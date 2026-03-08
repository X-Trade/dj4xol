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
        self.assertContains(response, 'Exploration &amp; First Turns')
        self.assertContains(response, 'How to Colonise')
        self.assertContains(response, 'Colony Management Basics')
        self.assertContains(response, 'Mining, Salvage &amp; Asteroids')
        self.assertContains(response, 'Colony Calculator')
        self.assertContains(response, 'Technology Directory')
        self.assertContains(response, 'Fleet Composition')
        self.assertContains(response, 'Research &amp; Labs')
        self.assertContains(response, 'Space Combat')
        self.assertContains(response, 'Invasion')

    def test_help_exploration_renders(self):
        response = self.client.get(reverse('dj4xol:help_exploration'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Exploration &amp; First Turns')
        self.assertContains(response, 'scanner')
        self.assertContains(response, 'Toggle scanner overlay')
        self.assertContains(response, 'inside advanced range')
        self.assertContains(response, 'inside basic range')
        self.assertContains(response, 'out of range')

    def test_help_colonising_renders(self):
        response = self.client.get(reverse('dj4xol:help_colonising'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'How to Colonise')
        self.assertContains(response, 'Colonise')

    def test_help_colony_management_renders(self):
        response = self.client.get(reverse('dj4xol:help_colony_management'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Colony Management Basics')
        self.assertContains(response, 'mines')

    def test_help_mining_salvage_renders(self):
        response = self.client.get(reverse('dj4xol:help_mining_salvage'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mining, Salvage &amp; Asteroids')
        self.assertContains(response, 'Remote Mine')

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

    def test_help_fleet_composition_renders(self):
        response = self.client.get(reverse('dj4xol:help_fleet_composition'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fleet Composition')
        self.assertContains(response, 'Subject to change')

    def test_help_research_labs_renders(self):
        response = self.client.get(reverse('dj4xol:help_research_labs'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Research &amp; Labs')
        self.assertContains(response, 'Lab Output')

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

    def test_help_technology_category_counts_show_full_totals(self):
        energy = ResearchCategory.objects.create(
            code='ENERCNT',
            name='Energy',
            display_order=10,
            enabled=True,
        )
        materials = ResearchCategory.objects.create(
            code='MATCNT',
            name='Materials',
            display_order=20,
            enabled=True,
        )
        Technology.objects.create(
            category=energy,
            level=1,
            name='Laser A',
            tech_type='ENERGY_WEAPON',
            enabled=True,
        )
        Technology.objects.create(
            category=energy,
            level=2,
            name='Laser B',
            tech_type='ENERGY_WEAPON',
            enabled=True,
        )
        Technology.objects.create(
            category=materials,
            level=1,
            name='Shield A',
            tech_type='SHIELD',
            enabled=True,
        )

        response = self.client.get(reverse('dj4xol:help_technology'))
        self.assertEqual(response.status_code, 200)

        categories = {c.id: c for c in response.context['categories']}
        self.assertEqual(categories[energy.id].tech_count, 2)
        self.assertEqual(categories[materials.id].tech_count, 1)
