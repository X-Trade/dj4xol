from django.core import mail
from django.test import override_settings
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from ..email_rollups import send_message_rollup_for_account
from ..models import Account, DiplomaticContract, ServerSettings
from ._util import default_game, get_default_race


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


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TestGenericEmailAction(TestCase):
    def setUp(self):
        ServerSettings.objects.update_or_create(
            key='enable_email',
            defaults={
                'value': 'True',
                'description': 'Enable outbound email',
            }
        )
        ServerSettings.objects.update_or_create(
            key='server_url',
            defaults={
                'value': 'https://example.test',
                'description': 'Server URL',
            }
        )
        self.user = User.objects.create_user(
            'staffer', 'staffer@example.com', 'pw'
        )
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        self.account = Account.objects.create(
            django_user=self.user,
            alias='staffer',
            email='staffer@example.com',
            full_name='Staff User',
            email_game_updates=False,
            email_game_rollups_per_day=0,
            email_newsletter=False,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_staff_action_sends_generic_test_email(self):
        response = self.client.get(reverse('dj4xol:test_generic_email'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dj4xol:index'))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, 'DJ4XOL: Test email')
        self.assertEqual(message.to, ['staffer@example.com'])
        self.assertIn('generic DJ4XOL test email', message.body)
        self.assertIn('there are no message-rollup updates to send', message.body)
        self.assertIn('Profile URL: https://example.test', message.body)
        self.assertIn('/4x/profile/', message.body)
        self.assertIn('Unsubscribe URL: https://example.test', message.body)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TestDiplomaticContractRollups(TestCase):
    def setUp(self):
        ServerSettings.objects.update_or_create(
            key='enable_email',
            defaults={'value': 'True', 'description': 'Enable outbound email'},
        )
        ServerSettings.objects.update_or_create(
            key='server_url',
            defaults={'value': 'https://example.test', 'description': 'Server URL'},
        )
        self.game = default_game(stars=6, fleets=0)
        self.player = self.game.players.first()
        self.account = self.player.account
        self.game.joinable = True
        self.game.save(update_fields=['joinable'])
        self.account.email = 'rollup_player@example.com'
        self.account.save(update_fields=['email'])

        other_user = User.objects.create_user('rollup_other', 'rollup_other@example.com', 'pw')
        other_account = Account.objects.create(
            django_user=other_user,
            alias='ROLL',
            email='rollup_other@example.com',
            full_name='Rollup Other',
        )
        from ..factory import GameFactory
        self.other_player = GameFactory(self.game).join_player(other_account, get_default_race())
        self.account.email_game_updates = True
        self.account.email_game_rollups_per_day = 1
        self.account.save(update_fields=['email_game_updates', 'email_game_rollups_per_day'])

    def test_rollup_includes_unhandled_contract_alert(self):
        DiplomaticContract.objects.create(
            game=self.game,
            sender=self.other_player,
            recipient=self.player,
            temperature='REQUEST',
            status='SENT',
            sent_year=self.game.year,
            expires_year=self.game.year + 24,
            request_clause_type='STANCE',
            request_stance='NEUTRAL',
            offer_clause_type='NOTHING',
        )

        sent, reason = send_message_rollup_for_account(self.account)

        self.assertTrue(sent, reason)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Diplomatic request:', mail.outbox[0].body)
        self.assertIn('Expires Year %s' % (self.game.year + 24), mail.outbox[0].body)
        self.assertNotIn('(%s)' % self.other_player.account.alias, mail.outbox[0].body)
