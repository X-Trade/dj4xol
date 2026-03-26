from django.test import Client, TestCase
from django.urls import reverse

from ..models import (
    CustomHelpPage,
    CustomHelpPageBlock,
    ResearchCategory,
    ServerSettings,
    Technology,
)
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
        self.assertContains(response, 'Race Type Browser')
        self.assertContains(response, 'Technology Directory')
        self.assertContains(response, 'Fleet Composition')
        self.assertContains(response, 'Research &amp; Labs')
        self.assertContains(response, 'Space Combat')
        self.assertContains(response, 'Diplomacy')
        self.assertContains(response, 'Invasion')
        self.assertContains(response, 'class="game-entry-title"', html=False)
        self.assertContains(response, 'class="game-meta"', html=False)

        content = response.content.decode('utf-8')
        self.assertLess(
            content.index('Race Type Browser'),
            content.index('Technology Directory'),
        )

    def test_help_index_shows_published_custom_pages_only(self):
        published_page = CustomHelpPage.objects.create(
            slug='server-rules',
            title='Server Rules',
            summary='House rules for this server.',
            nav_order=1,
            published=True,
        )
        CustomHelpPageBlock.objects.create(
            page=published_page,
            heading='Rules',
            body='Be kind to other players.',
        )
        CustomHelpPage.objects.create(
            slug='draft-page',
            title='Draft Page',
            published=False,
        )

        response = self.client.get(reverse('dj4xol:help_index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Server Rules')
        self.assertContains(response, 'House rules for this server.')
        self.assertNotContains(response, 'Draft Page')

        content = response.content.decode('utf-8')
        self.assertLess(
            content.index('104: Mining, Salvage &amp; Asteroids'),
            content.index('Server Rules'),
        )
        self.assertLess(
            content.index('Server Rules'),
            content.index('Fleet Composition'),
        )

    def test_custom_help_page_renders_blocks_links_and_images(self):
        page = CustomHelpPage.objects.create(
            slug='server-rules',
            title='Server Rules',
            tagline='Read before joining',
            summary='House rules for this server.',
            published=True,
        )
        CustomHelpPageBlock.objects.create(
            page=page,
            display_order=10,
            heading='Basics',
            body=(
                'See [the lobby](/4x/).\n\n'
                '- Stay respectful\n'
                '- Keep games moving\n\n'
                '![Map](https://example.test/map.png)'
            ),
        )

        response = self.client.get(
            reverse('dj4xol:custom_help_page', args=[page.slug])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Server Rules')
        self.assertContains(response, 'Read before joining')
        self.assertContains(response, 'Basics')
        self.assertContains(response, '<a href="/4x/">the lobby</a>', html=True)
        self.assertContains(response, '<ul class="rich-text-list">', html=False)
        self.assertContains(
            response,
            '<img class="rich-text-image" src="https://example.test/map.png" alt="Map">',
            html=True,
        )

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
        self.assertContains(response, 'Colony Administration')

    def test_help_anomalies_renders(self):
        response = self.client.get(reverse('dj4xol:help_anomalies'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Anomalies')
        self.assertContains(response, 'Danger &amp; Stability')
        self.assertContains(response, 'Outcome Pattern')

    def test_help_mining_salvage_renders(self):
        response = self.client.get(reverse('dj4xol:help_mining_salvage'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mining, Salvage &amp; Asteroids')
        self.assertContains(response, 'Remote Mine')
        self.assertContains(response, 'jettisoned cargo dumped into space is safe to recover')

    def test_help_space_combat_renders(self):
        response = self.client.get(reverse('dj4xol:help_space_combat'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Space Combat')
        self.assertContains(response, 'Damage Resolution')

    def test_help_diplomacy_renders(self):
        response = self.client.get(reverse('dj4xol:help_diplomacy'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Diplomacy')
        self.assertContains(response, 'Effect on Combat Initiation')
        self.assertContains(response, 'Readiness Advantage')

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

    def test_help_technology_type_dropdown_is_alphabetised(self):
        response = self.client.get(reverse('dj4xol:help_technology'))
        self.assertEqual(response.status_code, 200)
        labels = [label for _code, label in response.context['tech_type_choices']]
        self.assertEqual(labels, sorted(labels, key=lambda label: label.lower()))

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

    def test_help_technology_shows_race_type_requirement_in_english(self):
        energy = ResearchCategory.objects.create(
            code='ENERGATE',
            name='Energy',
            display_order=10,
            enabled=True,
        )
        Technology.objects.create(
            category=energy,
            level=2,
            name='War Shield',
            tech_type='SHIELD',
            params_json='{"defense_level": 1.0, "race_type": "not JOAT"}',
            enabled=True,
        )

        response = self.client.get(reverse('dj4xol:help_technology'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Race Type')
        self.assertContains(response, 'Is not JOAT')

    def test_home_welcome_renders_rich_text(self):
        ServerSettings.objects.update_or_create(
            key='server_welcome',
            defaults={
                'value': '',
                'long_value': (
                    'Welcome to [DJ4XOL](/4x/).\n\n'
                    '![Hero](https://example.test/hero.png)'
                ),
                'description': 'Welcome message on homepage',
            },
        )

        response = self.client.get(reverse('dj4xol:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<a href="/4x/">DJ4XOL</a>', html=True)
        self.assertContains(
            response,
            '<img class="rich-text-image" src="https://example.test/hero.png" alt="Hero">',
            html=True,
        )


class HelpPageCmsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user, _ = get_default_user()
        self.client.force_login(self.user)

    def test_non_staff_cannot_access_help_page_cms(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('dj4xol:help_pages_cms'))

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'Staff access is required.', status_code=403)

    def test_staff_can_create_help_page_with_block(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('dj4xol:help_pages_cms'),
            {
                'page_id': 'new',
                'title': 'Server Rules',
                'slug': 'server-rules',
                'tagline': 'Read before joining',
                'summary': 'House rules for this server.',
                'nav_order': '5',
                'published': 'on',
                'blocks-TOTAL_FORMS': '1',
                'blocks-INITIAL_FORMS': '0',
                'blocks-MIN_NUM_FORMS': '0',
                'blocks-MAX_NUM_FORMS': '1000',
                'blocks-0-display_order': '10',
                'blocks-0-heading': 'Basics',
                'blocks-0-body': 'Stay respectful.\n- No ghosting',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Help page saved.')
        self.assertTrue(
            CustomHelpPage.objects.filter(slug='server-rules').exists()
        )
        page = CustomHelpPage.objects.get(slug='server-rules')
        self.assertEqual(page.title, 'Server Rules')
        self.assertEqual(page.blocks.count(), 1)
        self.assertEqual(page.blocks.first().heading, 'Basics')
        self.assertContains(response, 'Open Public Preview')

    def test_help_technology_humanises_trait_requirement_names(self):
        energy = ResearchCategory.objects.create(
            code='ENERTRAIT',
            name='Energy',
            display_order=10,
            enabled=True,
        )
        Technology.objects.create(
            category=energy,
            level=2,
            name='Trait Gate',
            tech_type='OTHER',
            params_json='{"race_type": "has has_advanced_remoteminers"}',
            enabled=True,
        )

        response = self.client.get(reverse('dj4xol:help_technology'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Has advanced remote miners')
