from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from ..models import Account, ServerSettings


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
