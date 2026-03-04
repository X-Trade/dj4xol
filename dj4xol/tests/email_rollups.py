from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from ..models import Account


class EmailUnsubscribeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('tester', 'tester@example.com', 'pw')
        self.account = Account.objects.create(
            django_user=self.user,
            alias='tester',
            email='tester@example.com',
            full_name='Tester',
            email_game_updates=True,
            email_game_rollups_per_day=2,
            email_newsletter=False,
        )
        self.client = Client()

    def test_unsubscribe_view_updates_preferences(self):
        key = self.account.email_unsubscribe_key
        url = reverse('dj4xol:unsubscribe_email', args=[key])
        response = self.client.post(url, {
            'email_game_rollups_per_day': '0',
            'email_game_updates': 'on',
            'email_newsletter': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.account.refresh_from_db()
        self.assertTrue(self.account.email_game_updates)
        self.assertEqual(self.account.email_game_rollups_per_day, 1)
        self.assertTrue(self.account.email_newsletter)

    def test_unsubscribe_view_invalid_key(self):
        url = reverse('dj4xol:unsubscribe_email', args=['0' * 32])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid or expired unsubscribe link.')

    def test_unsubscribe_turns_off_updates(self):
        key = self.account.email_unsubscribe_key
        url = reverse('dj4xol:unsubscribe_email', args=[key])
        response = self.client.post(url, {'email_game_rollups_per_day': '0'})
        self.assertEqual(response.status_code, 200)
        self.account.refresh_from_db()
        self.assertFalse(self.account.email_game_updates)
        self.assertEqual(self.account.email_game_rollups_per_day, 0)
        self.assertFalse(self.account.email_newsletter)
