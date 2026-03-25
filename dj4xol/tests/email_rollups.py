from django.core import mail
from django.test import override_settings
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from ..email_rollups import (
    send_email_verification_for_account,
    send_game_deleted_email,
    send_game_invite_email,
    send_game_join_email,
    send_message_rollup_for_account,
)
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
            email_verified=True,
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
            email_verified=True,
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
        self.assertEqual(len(getattr(message, 'alternatives', [])), 0)

    def test_staff_action_sends_generic_test_html_email_when_enabled(self):
        self.account.email_html_enabled = True
        self.account.theme = 'win95'
        self.account.save(update_fields=['email_html_enabled', 'theme'])

        response = self.client.get(reverse('dj4xol:test_generic_email'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dj4xol:index'))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        alternatives = getattr(message, 'alternatives', [])
        self.assertEqual(len(alternatives), 1)
        self.assertEqual(alternatives[0][1], 'text/html')
        self.assertIn('email-theme-win95', alternatives[0][0])
        self.assertIn('Test Email', alternatives[0][0])

    def test_staff_action_blocks_generic_test_email_for_unverified_account(self):
        self.account.email_verified = False
        self.account.save(update_fields=['email_verified'])

        response = self.client.get(reverse('dj4xol:test_generic_email'), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Generic test email not sent: Email not verified.',
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_verification_email_remains_text_only_even_with_html_enabled(self):
        self.account.email_html_enabled = True
        self.account.save(update_fields=['email_html_enabled'])

        sent, reason = send_email_verification_for_account(self.account)

        self.assertTrue(sent, reason)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn('Verify email:', message.body)
        self.assertEqual(len(getattr(message, 'alternatives', [])), 0)


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
        self.account.email_verified = True
        self.account.save(update_fields=['email', 'email_verified'])

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

    def test_rollup_skips_unverified_account(self):
        self.account.email_verified = False
        self.account.save(update_fields=['email_verified'])

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

        self.assertFalse(sent)
        self.assertEqual(reason, 'Email not verified')
        self.assertEqual(len(mail.outbox), 0)

    def test_invite_email_skips_unverified_account(self):
        game = default_game(stars=5, fleets=0)
        invitee_user = User.objects.create_user(
            'invitee_unverified',
            'invitee@example.com',
            'pw',
        )
        Account.objects.create(
            django_user=invitee_user,
            alias='INV',
            email='invitee@example.com',
            full_name='Invitee User',
            email_verified=False,
        )

        sent = send_game_invite_email(game, 'invitee@example.com')

        self.assertFalse(sent)
        self.assertEqual(len(mail.outbox), 0)

    def test_join_email_skips_unverified_owner_account(self):
        game = default_game(stars=6, fleets=0)
        owner_account = game.owner
        owner_account.email = 'owner@example.com'
        owner_account.email_verified = False
        owner_account.email_game_updates = True
        owner_account.save(
            update_fields=['email', 'email_verified', 'email_game_updates']
        )

        joiner_user = User.objects.create_user(
            'joiner_mail_test',
            'joiner-mail@example.com',
            'pw',
        )
        joiner_account = Account.objects.create(
            django_user=joiner_user,
            alias='JOIN',
            email='joiner-mail@example.com',
            full_name='Join Mail',
            email_verified=True,
        )

        sent = send_game_join_email(game, owner_account, joiner_account)

        self.assertFalse(sent)
        self.assertEqual(len(mail.outbox), 0)

    def test_deleted_game_email_skips_unverified_player_account(self):
        game = default_game(stars=6, fleets=0)
        owner_account = game.owner

        other_user = User.objects.create_user(
            'deleted_mail_test',
            'deleted-mail@example.com',
            'pw',
        )
        other_account = Account.objects.create(
            django_user=other_user,
            alias='DELD',
            email='deleted-mail@example.com',
            full_name='Deleted Mail',
            email_verified=False,
            email_game_updates=True,
        )

        sent = send_game_deleted_email(game, owner_account, other_account)

        self.assertFalse(sent)
        self.assertEqual(len(mail.outbox), 0)

    def test_verification_email_regenerates_blank_legacy_key(self):
        legacy_user = User.objects.create_user(
            'legacyverify',
            'legacyverify@example.com',
            'pw',
        )
        legacy_account = Account.objects.create(
            django_user=legacy_user,
            alias='LEG',
            email='legacyverify@example.com',
            full_name='Legacy Verify',
        )
        legacy_account.email_verification_key = ''
        legacy_account.save(update_fields=['email_verification_key'])

        sent, reason = send_email_verification_for_account(legacy_account)

        self.assertTrue(sent, reason)
        legacy_account.refresh_from_db()
        self.assertTrue(bool(legacy_account.email_verification_key))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            legacy_account.email_verification_key,
            mail.outbox[0].body,
        )
