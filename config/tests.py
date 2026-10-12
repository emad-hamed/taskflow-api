import json
import os
import subprocess
import sys

from django.test import SimpleTestCase


class EnvironmentSettingsTests(SimpleTestCase):
    def load_settings(self, **overrides):
        environment = {
            key: value for key, value in os.environ.items()
            if key not in {'DJANGO_SECRET_KEY', 'DJANGO_DEBUG', 'DJANGO_ALLOWED_HOSTS', 'TASKFLOW_DB_PATH'}
        }
        environment.update(overrides)
        return subprocess.run(
            [sys.executable, '-c',
             'import json; from config import settings as s; '
             'print(json.dumps([s.DEBUG, s.ALLOWED_HOSTS, str(s.DATABASES["default"]["NAME"])]))'],
            env=environment, capture_output=True, text=True, check=False,
        )

    def test_missing_or_short_key_fails_closed(self):
        for overrides in [{}, {'DJANGO_SECRET_KEY': 'short'}]:
            with self.subTest(overrides=overrides):
                result = self.load_settings(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('ImproperlyConfigured', result.stderr)

    def test_debug_defaults_off_and_hosts_are_local(self):
        result = self.load_settings(DJANGO_SECRET_KEY='test-only-key-' * 5)
        self.assertEqual(result.returncode, 0, result.stderr)
        debug, hosts, _ = json.loads(result.stdout)
        self.assertFalse(debug)
        self.assertEqual(hosts, ['localhost', '127.0.0.1'])

    def test_environment_overrides(self):
        result = self.load_settings(
            DJANGO_SECRET_KEY='test-only-key-' * 5, DJANGO_DEBUG='true',
            DJANGO_ALLOWED_HOSTS='localhost, example.test, ', TASKFLOW_DB_PATH='alternate.sqlite3',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [True, ['localhost', 'example.test'], 'alternate.sqlite3'])

    def test_invalid_debug_value_is_rejected(self):
        result = self.load_settings(DJANGO_SECRET_KEY='test-only-key-' * 5, DJANGO_DEBUG='yes')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_DEBUG must be true or false', result.stderr)
