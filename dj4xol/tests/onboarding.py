from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from ..name_rules import parse_profanity_terms, validate_safe_public_text
from ..models import Account, Player, ServerRace, ServerSettings
from ._util import default_game, get_default_race_type


class OnboardingRegistrationTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_register_blocks_anonymous_when_self_signup_disabled(self):
        ServerSettings.objects.update_or_create(
            key='allow_self_signup',
            defaults={
                'value': 'False',
                'description': 'Allow self-sign-up',
            }
        )
        response = self.client.get(reverse('dj4xol:register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Self-sign-up is disabled on this server.')

    def test_register_creates_user_and_account_when_anonymous(self):
        ServerSettings.objects.update_or_create(
            key='allow_self_signup',
            defaults={
                'value': 'True',
                'description': 'Allow self-sign-up',
            }
        )
        response = self.client.post(reverse('dj4xol:register'), {
            'username': 'newpilot',
            'password1': 'pw-test-12345',
            'password2': 'pw-test-12345',
            'alias': 'newpilot',
            'email': 'pilot@example.com',
            'full_name': 'New Pilot',
            'website_url': '',
            'email_game_updates': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dj4xol:onboarding_theme'))
        self.assertTrue(User.objects.filter(username='newpilot').exists())
        user = User.objects.get(username='newpilot')
        self.assertTrue(Account.objects.filter(django_user=user).exists())
        account = Account.objects.get(django_user=user)
        self.assertEqual(account.onboarding_step, Account.ONBOARDING_STEP_THEME)
        self.assertTrue(account.email_game_updates)
        self.assertFalse(account.email_newsletter)
        self.assertEqual(account.email_game_rollups_per_day, 1)
        self.assertTrue(bool(account.email_unsubscribe_key))

    def test_register_shows_email_and_password_help_in_login_section(self):
        ServerSettings.objects.update_or_create(
            key='allow_self_signup',
            defaults={
                'value': 'True',
                'description': 'Allow self-sign-up',
            }
        )
        response = self.client.get(reverse('dj4xol:register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create Login')
        self.assertContains(response, 'Email')
        self.assertContains(response, 'Password')
        self.assertContains(response, 'Confirm Password')
        self.assertContains(response, 'Your password')
        self.assertContains(response, 'onboarding_profile.py')

    def test_register_hides_user_fields_for_logged_in_user(self):
        user = User.objects.create_user('existing', 'existing@example.com', 'pass1234')
        self.client.force_login(user)
        response = self.client.get(reverse('dj4xol:register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create Your 4x Profile')
        self.assertNotContains(response, 'Create Login')

    def test_gamelist_redirects_incomplete_account_to_onboarding_theme(self):
        user = User.objects.create_user('themewait', 'themewait@example.com', 'pass1234')
        Account.objects.create(
            django_user=user,
            alias='themewait',
            email='themewait@example.com',
            full_name='Theme Wait',
            onboarding_step=Account.ONBOARDING_STEP_THEME,
        )
        self.client.force_login(user)

        response = self.client.get(reverse('dj4xol:index'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dj4xol:onboarding_theme'))

    def test_gamelist_redirects_incomplete_account_to_onboarding_race(self):
        user = User.objects.create_user('racewait', 'racewait@example.com', 'pass1234')
        Account.objects.create(
            django_user=user,
            alias='racewait',
            email='racewait@example.com',
            full_name='Race Wait',
            onboarding_step=Account.ONBOARDING_STEP_RACE,
        )
        self.client.force_login(user)

        response = self.client.get(reverse('dj4xol:index'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dj4xol:onboarding_race'))

    def test_profile_updates_email_preferences(self):
        user = User.objects.create_user('prefs', 'prefs@example.com', 'pass1234')
        Account.objects.create(
            django_user=user,
            alias='prefs',
            email='prefs@example.com',
            full_name='Prefs User',
            email_game_updates=True,
            email_game_rollups_per_day=2,
            email_newsletter=True,
        )
        self.client.force_login(user)
        response = self.client.post(
            reverse('dj4xol:update_email_preferences'),
            {'email_game_updates': 'on'},
        )
        self.assertEqual(response.status_code, 200)
        account = Account.objects.get(django_user=user)
        self.assertTrue(account.email_game_updates)
        self.assertFalse(account.email_newsletter)
        self.assertEqual(account.email_game_rollups_per_day, 1)
        self.assertTrue(bool(account.email_unsubscribe_key))

    def test_register_rejects_reserved_abandoned_name(self):
        ServerSettings.objects.update_or_create(
            key='allow_self_signup',
            defaults={
                'value': 'True',
                'description': 'Allow self-sign-up',
            }
        )
        response = self.client.post(reverse('dj4xol:register'), {
            'username': 'Abandoned',
            'password1': 'pw-test-12345',
            'password2': 'pw-test-12345',
            'alias': 'Abandoned',
            'email': 'pilot@example.com',
            'full_name': 'New Pilot',
            'website_url': '',
            'email_game_updates': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Username is reserved.')
        self.assertContains(response, 'Account name is reserved.')
        self.assertFalse(User.objects.filter(username='Abandoned').exists())

    def test_register_rejects_profane_alias_and_non_ascii_full_name(self):
        ServerSettings.objects.update_or_create(
            key='allow_self_signup',
            defaults={
                'value': 'True',
                'description': 'Allow self-sign-up',
            }
        )
        response = self.client.post(reverse('dj4xol:register'), {
            'username': 'newpilot',
            'password1': 'pw-test-12345',
            'password2': 'pw-test-12345',
            'alias': 'fuckpilot',
            'email': 'pilot@example.com',
            'full_name': 'New Pilot 😎',
            'website_url': '',
            'email_game_updates': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Account name contains blocked profanity.')
        self.assertContains(response, 'Full name contains unsupported characters.')
        self.assertFalse(User.objects.filter(username='newpilot').exists())

    def test_register_allows_profane_alias_when_filter_disabled(self):
        ServerSettings.objects.update_or_create(
            key='allow_self_signup',
            defaults={
                'value': 'True',
                'description': 'Allow self-sign-up',
            }
        )
        ServerSettings.objects.update_or_create(
            key='enable_profanity_filter',
            defaults={
                'value': 'False',
                'description': 'Enable profanity filter',
            }
        )
        response = self.client.post(reverse('dj4xol:register'), {
            'username': 'fuckpilot',
            'password1': 'pw-test-12345',
            'password2': 'pw-test-12345',
            'alias': 'fuckpilot',
            'email': 'pilot@example.com',
            'full_name': 'New Pilot',
            'website_url': '',
            'email_game_updates': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='fuckpilot').exists())


class IdentityNameRulesTest(TestCase):
    def test_safe_public_text_rejects_markup_characters(self):
        with self.assertRaises(ValidationError):
            validate_safe_public_text('Bad <script>alert(1)</script>', 'Name')

    def test_safe_public_text_rejects_profanity(self):
        with self.assertRaises(ValidationError):
            validate_safe_public_text('Captain fuckface', 'Name')

    def test_safe_public_text_rejects_spaced_or_dotted_profanity(self):
        with self.assertRaises(ValidationError):
            validate_safe_public_text(
                'Captain f . u c k face',
                'Name',
                profanity_whitelist=set(),
                profanity_blacklist=set(),
            )

    def test_safe_public_text_whitelist_can_override_false_positive(self):
        self.assertEqual(
            validate_safe_public_text(
                'Scunthorpe',
                'Name',
                profanity_whitelist=parse_profanity_terms('scunthorpe'),
                profanity_blacklist=set(),
            ),
            'Scunthorpe',
        )

    def test_safe_public_text_blacklist_can_add_server_specific_term(self):
        with self.assertRaises(ValidationError):
            validate_safe_public_text(
                'Void Admiral',
                'Name',
                profanity_whitelist=set(),
                profanity_blacklist=parse_profanity_terms('void'),
            )

    def test_server_race_name_cannot_be_abandoned(self):
        with self.assertRaises(ValidationError):
            ServerRace.objects.create(
                name='Abandoned',
                plural_name='Abandoned',
                race_type=get_default_race_type(),
            )

    def test_player_name_cannot_be_abandoned(self):
        game = default_game()
        with self.assertRaises(ValidationError):
            Player.objects.create(
                game=game,
                account=game.owner,
                name='Abandoned',
                plural_name='Abandoned',
                race_type=get_default_race_type(),
            )
