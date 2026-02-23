import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from ..models import Account, GameInvitation, ServerRace
from ._util import get_default_race_type


class InviteLookupApiTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner_user = User.objects.create_user(
            username='owner',
            email='owner@example.com',
            password='pw-test-12345',
        )
        self.owner_account = Account.objects.create(
            django_user=self.owner_user,
            alias='owner',
            full_name='Owner',
            email='owner@example.com',
        )
        self.target_user = User.objects.create_user(
            username='targetuser',
            email='target@example.com',
            password='pw-test-12345',
        )
        self.target_account = Account.objects.create(
            django_user=self.target_user,
            alias='TargetAlias',
            full_name='Target',
            email='target@example.com',
        )
        self.client.force_login(self.owner_user)

    def test_account_lookup_returns_alias_username_without_email(self):
        response = self.client.get(
            reverse('dj4xol:account_lookup'),
            {'q': 'target'},
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertTrue(payload['results'])
        first = payload['results'][0]
        self.assertIn('alias', first)
        self.assertIn('username', first)
        self.assertIn('value', first)
        self.assertNotIn('email', first)

    def test_account_lookup_resolves_exact_email_to_alias(self):
        response = self.client.get(
            reverse('dj4xol:account_lookup'),
            {'q': 'target@example.com'},
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertTrue(payload['results'])
        matches = [item for item in payload['results'] if item.get('match') == 'email']
        self.assertTrue(matches)
        self.assertEqual(matches[0]['value'], 'TargetAlias')


class InviteAliasResolutionTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner_user = User.objects.create_user(
            username='gameowner',
            email='gameowner@example.com',
            password='pw-test-12345',
        )
        self.owner_account = Account.objects.create(
            django_user=self.owner_user,
            alias='gameowner',
            full_name='Game Owner',
            email='gameowner@example.com',
        )
        self.invited_user = User.objects.create_user(
            username='fleetpilot',
            email='fleetpilot@example.com',
            password='pw-test-12345',
        )
        self.invited_account = Account.objects.create(
            django_user=self.invited_user,
            alias='FleetPilot',
            full_name='Fleet Pilot',
            email='fleetpilot@example.com',
        )
        self.race = ServerRace.objects.create(
            name='Owner Race',
            plural_name='Owner Races',
            race_type=get_default_race_type(),
            owner=self.owner_account,
        )
        self.client.force_login(self.owner_user)

    def test_create_game_invites_by_alias(self):
        response = self.client.post(reverse('dj4xol:create_game'), {
            'name': 'Alias Invite Test',
            'description': '',
            'starting_year': 2400,
            'map_size_x': 128,
            'map_size_y': 128,
            'num_stars': 30,
            'turn_scheme': 'QUORUM',
            'years_per_turn': 1,
            'race': str(self.race.id),
            'invitations': 'FleetPilot',
        })
        self.assertEqual(response.status_code, 302)
        invitation = GameInvitation.objects.filter(account=self.invited_account).first()
        self.assertIsNotNone(invitation)
