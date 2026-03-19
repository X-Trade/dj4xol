import re

from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
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
        self.assertFalse(account.email_verified)
        self.assertTrue(bool(account.email_verification_key))

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
        self.assertContains(response, 'name="website_url"', html=False)
        self.assertContains(response, 'placeholder="optional"', html=False)
        self.assertContains(response, 'data-url-prefix="https://"', html=False)
        self.assertContains(response, 'name="full_name"', html=False)
        self.assertContains(response, 'autocapitalize="words"', html=False)

    def test_register_hides_user_fields_for_logged_in_user(self):
        user = User.objects.create_user('existing', 'existing@example.com', 'pass1234')
        self.client.force_login(user)
        response = self.client.get(reverse('dj4xol:register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create Your 4x Profile')
        self.assertNotContains(response, 'Create Login')

    def test_login_shows_forgot_password_link(self):
        response = self.client.get(reverse('login'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Forgot password?')
        self.assertContains(response, reverse('password_reset'))

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

    def test_onboarding_theme_uses_horizontal_carousel_markup(self):
        user = User.objects.create_user('themepanel', 'themepanel@example.com', 'pass1234')
        Account.objects.create(
            django_user=user,
            alias='themepanel',
            email='themepanel@example.com',
            full_name='Theme Panel',
            onboarding_step=Account.ONBOARDING_STEP_THEME,
        )
        self.client.force_login(user)

        response = self.client.get(reverse('dj4xol:onboarding_theme'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="theme-selector-panel"', html=False)
        self.assertContains(response, 'class="theme-selector-frame"', html=False)
        self.assertContains(response, 'class="theme-selector"', html=False)
        self.assertContains(response, 'class="theme-carousel-button theme-carousel-button--prev"', html=False)

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

    def test_register_accepts_valid_website_url(self):
        ServerSettings.objects.update_or_create(
            key='allow_self_signup',
            defaults={
                'value': 'True',
                'description': 'Allow self-sign-up',
            }
        )
        response = self.client.post(reverse('dj4xol:register'), {
            'username': 'sitepilot',
            'password1': 'pw-test-12345',
            'password2': 'pw-test-12345',
            'alias': 'sitepilot',
            'email': 'pilot@example.com',
            'full_name': 'Site Pilot',
            'website_url': 'example.com/profile',
            'email_game_updates': 'on',
        })
        self.assertEqual(response.status_code, 302)
        account = Account.objects.get(django_user__username='sitepilot')
        self.assertEqual(account.website_url, 'https://example.com/profile')

    def test_register_rejects_invalid_website_url(self):
        ServerSettings.objects.update_or_create(
            key='allow_self_signup',
            defaults={
                'value': 'True',
                'description': 'Allow self-sign-up',
            }
        )
        response = self.client.post(reverse('dj4xol:register'), {
            'username': 'badsite',
            'password1': 'pw-test-12345',
            'password2': 'pw-test-12345',
            'alias': 'badsite',
            'email': 'pilot@example.com',
            'full_name': 'Bad Site',
            'website_url': 'not a url',
            'email_game_updates': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter a valid URL.')
        self.assertFalse(User.objects.filter(username='badsite').exists())

    def test_register_treats_placeholder_prefix_only_as_blank(self):
        ServerSettings.objects.update_or_create(
            key='allow_self_signup',
            defaults={
                'value': 'True',
                'description': 'Allow self-sign-up',
            }
        )
        response = self.client.post(reverse('dj4xol:register'), {
            'username': 'prefixpilot',
            'password1': 'pw-test-12345',
            'password2': 'pw-test-12345',
            'alias': 'prefixpilot',
            'email': 'pilot@example.com',
            'full_name': 'Prefix Pilot',
            'website_url': 'https://',
            'email_game_updates': 'on',
        })
        self.assertEqual(response.status_code, 302)
        account = Account.objects.get(django_user__username='prefixpilot')
        self.assertEqual(account.website_url, '')

    def test_register_capitalises_full_name_word_starts(self):
        ServerSettings.objects.update_or_create(
            key='allow_self_signup',
            defaults={
                'value': 'True',
                'description': 'Allow self-sign-up',
            }
        )
        response = self.client.post(reverse('dj4xol:register'), {
            'username': 'namepilot',
            'password1': 'pw-test-12345',
            'password2': 'pw-test-12345',
            'alias': 'namepilot',
            'email': 'pilot@example.com',
            'full_name': 'new pilot example',
            'website_url': '',
            'email_game_updates': 'on',
        })
        self.assertEqual(response.status_code, 302)
        account = Account.objects.get(django_user__username='namepilot')
        self.assertEqual(account.full_name, 'New Pilot Example')

    def test_register_sends_verification_email_when_enabled(self):
        ServerSettings.objects.update_or_create(
            key='allow_self_signup',
            defaults={
                'value': 'True',
                'description': 'Allow self-sign-up',
            }
        )
        ServerSettings.objects.update_or_create(
            key='enable_email',
            defaults={
                'value': 'True',
                'description': 'Enable email',
            }
        )
        ServerSettings.objects.update_or_create(
            key='server_url',
            defaults={
                'value': 'https://example.test',
                'description': 'Server URL',
            }
        )

        response = self.client.post(reverse('dj4xol:register'), {
            'username': 'mailpilot',
            'password1': 'pw-test-12345',
            'password2': 'pw-test-12345',
            'alias': 'mailpilot',
            'email': 'pilot@example.com',
            'full_name': 'Mail Pilot',
            'website_url': '',
            'email_game_updates': 'on',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Verification email sent.')
        self.assertEqual(len(mail.outbox), 1)
        account = Account.objects.get(django_user__username='mailpilot')
        self.assertIn(account.email_verification_key, mail.outbox[0].body)
        self.assertIn('/verify-email/', mail.outbox[0].body)

    def test_verify_email_marks_account_verified_and_redirects_to_profile(self):
        user = User.objects.create_user(
            'verifypilot', 'verify@example.com', 'pass1234'
        )
        account = Account.objects.create(
            django_user=user,
            alias='verifypilot',
            email='verify@example.com',
            full_name='Verify Pilot',
            onboarding_step=Account.ONBOARDING_STEP_COMPLETE,
        )

        response = self.client.get(
            reverse('dj4xol:verify_email', args=[account.email_verification_key]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        account.refresh_from_db()
        self.assertTrue(account.email_verified)
        self.assertContains(response, 'Email address verified.')
        self.assertContains(response, '4x Profile')

    def test_resend_email_verification_sends_email_from_profile(self):
        ServerSettings.objects.update_or_create(
            key='enable_email',
            defaults={
                'value': 'True',
                'description': 'Enable email',
            }
        )
        ServerSettings.objects.update_or_create(
            key='server_url',
            defaults={
                'value': 'https://example.test',
                'description': 'Server URL',
            }
        )
        user = User.objects.create_user(
            'resendpilot', 'resend@example.com', 'pass1234'
        )
        Account.objects.create(
            django_user=user,
            alias='resendpilot',
            email='resend@example.com',
            full_name='Resend Pilot',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('dj4xol:resend_email_verification'),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Verification email sent.')
        self.assertEqual(len(mail.outbox), 1)

    def test_profile_shows_change_email_button(self):
        user = User.objects.create_user(
            'changepilot', 'change@example.com', 'pass1234'
        )
        Account.objects.create(
            django_user=user,
            alias='changepilot',
            email='change@example.com',
            full_name='Change Pilot',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('dj4xol:profile'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Change email')
        self.assertContains(response, 'Change password')

    def test_change_email_updates_account_and_resets_verification(self):
        ServerSettings.objects.update_or_create(
            key='enable_email',
            defaults={
                'value': 'True',
                'description': 'Enable email',
            }
        )
        ServerSettings.objects.update_or_create(
            key='server_url',
            defaults={
                'value': 'https://example.test',
                'description': 'Server URL',
            }
        )
        user = User.objects.create_user(
            'emailchange', 'old@example.com', 'pass1234'
        )
        account = Account.objects.create(
            django_user=user,
            alias='emailchange',
            email='old@example.com',
            full_name='Email Change',
            email_verified=True,
        )
        old_key = account.email_verification_key
        self.client.force_login(user)

        response = self.client.post(
            reverse('dj4xol:profile'),
            {
                'action': 'change_email',
                'email': 'new@example.com',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        account.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(account.email, 'new@example.com')
        self.assertEqual(user.email, 'new@example.com')
        self.assertFalse(account.email_verified)
        self.assertNotEqual(account.email_verification_key, old_key)
        self.assertContains(
            response,
            'Email address updated. Verification email sent.',
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(account.email_verification_key, mail.outbox[0].body)

    def test_change_email_rejects_same_address_and_keeps_dialog_open(self):
        user = User.objects.create_user(
            'sameemail', 'same@example.com', 'pass1234'
        )
        account = Account.objects.create(
            django_user=user,
            alias='sameemail',
            email='same@example.com',
            full_name='Same Email',
            email_verified=True,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('dj4xol:profile'),
            {
                'action': 'change_email',
                'email': 'same@example.com',
            },
        )

        self.assertEqual(response.status_code, 200)
        account.refresh_from_db()
        self.assertEqual(account.email, 'same@example.com')
        self.assertTrue(account.email_verified)
        self.assertContains(response, 'Enter a different email address.')
        self.assertContains(response, 'id="change-email-overlay"', html=False)

    def test_change_password_updates_password(self):
        user = User.objects.create_user(
            'passwordpilot', 'password@example.com', 'old-pass-1234'
        )
        Account.objects.create(
            django_user=user,
            alias='passwordpilot',
            email='password@example.com',
            full_name='Password Pilot',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('dj4xol:profile'),
            {
                'action': 'change_password',
                'old_password': 'old-pass-1234',
                'new_password1': 'new-pass-12345',
                'new_password2': 'new-pass-12345',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Password updated.')
        user.refresh_from_db()
        self.assertTrue(user.check_password('new-pass-12345'))
        self.assertTrue('_auth_user_id' in self.client.session)

    def test_change_password_invalid_keeps_dialog_open(self):
        user = User.objects.create_user(
            'badpasswordpilot', 'badpassword@example.com', 'old-pass-1234'
        )
        Account.objects.create(
            django_user=user,
            alias='badpasswordpilot',
            email='badpassword@example.com',
            full_name='Bad Password Pilot',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('dj4xol:profile'),
            {
                'action': 'change_password',
                'old_password': 'wrong-pass',
                'new_password1': 'new-pass-12345',
                'new_password2': 'new-pass-12345',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please correct the highlighted password fields.')
        self.assertContains(response, 'id="change-password-overlay"', html=False)
        self.assertContains(response, 'name="old_password"', html=False)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_forgot_password_sends_reset_email_and_allows_password_reset(self):
        user = User.objects.create_user(
            'forgotpilot', 'forgot@example.com', 'old-pass-1234'
        )
        Account.objects.create(
            django_user=user,
            alias='forgotpilot',
            email='forgot@example.com',
            full_name='Forgot Pilot',
        )

        response = self.client.post(
            reverse('password_reset'),
            {'email': 'forgot@example.com'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'password reset link has been sent')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['forgot@example.com'])
        self.assertIn('DJ4XOL: Reset your password', mail.outbox[0].subject)
        match = re.search(r'http://testserver(/accounts/reset/[^\s]+/)', mail.outbox[0].body)
        self.assertIsNotNone(match)
        reset_path = match.group(1)

        response = self.client.get(reset_path, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Set New Password')
        reset_path = response.request['PATH_INFO']

        response = self.client.post(
            reset_path,
            {
                'new_password1': 'fresh-pass-12345',
                'new_password2': 'fresh-pass-12345',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Password Updated')
        self.assertTrue(self.client.login(
            username='forgotpilot',
            password='fresh-pass-12345',
        ))


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
