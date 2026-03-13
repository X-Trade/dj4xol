from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from ..models import ServerSettings


class TestMigrationDrift(TestCase):
    def test_no_unmigrated_model_changes(self):
        stdout = StringIO()
        stderr = StringIO()
        try:
            call_command(
                'makemigrations',
                check=True,
                dry_run=True,
                interactive=False,
                verbosity=0,
                stdout=stdout,
                stderr=stderr,
            )
        except SystemExit as exc:
            self.fail(
                'Django detected unmigrated model changes (exit %s).\nSTDOUT:\n%s\nSTDERR:\n%s'
                % (exc.code, stdout.getvalue(), stderr.getvalue())
            )


class TestServerSettings(TestCase):
    def tearDown(self):
        ServerSettings._defaults_cache = None  # Reset cache between tests

    def test_get_existing_setting(self):
        """Get a setting that already exists in the database."""
        ServerSettings.objects.create(
            key='test_key', value='test_value', description='Test'
        )
        self.assertEqual(ServerSettings.get('test_key'), 'test_value')

    def test_get_creates_from_fixtures(self):
        """Get a setting that doesn't exist but is in fixtures."""
        # server_name is in defaults.yaml
        self.assertFalse(ServerSettings.objects.filter(pk='server_name').exists())
        value = ServerSettings.get('server_name')
        self.assertEqual(value, "It's Full of Stars")
        # Should now exist in database
        self.assertTrue(ServerSettings.objects.filter(pk='server_name').exists())

    def test_get_returns_default_for_unknown(self):
        """Get a setting that doesn't exist anywhere returns default."""
        self.assertIsNone(ServerSettings.get('nonexistent_key'))
        self.assertEqual(ServerSettings.get('nonexistent_key', 'fallback'), 'fallback')

    def test_get_does_not_recreate_existing(self):
        """Get doesn't overwrite existing database values with fixture defaults."""
        ServerSettings.objects.create(
            key='server_name', value='Custom Name', description='Custom'
        )
        self.assertEqual(ServerSettings.get('server_name'), 'Custom Name')
