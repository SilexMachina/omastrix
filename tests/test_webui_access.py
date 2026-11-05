"""Local/network access policy; isolated profiles and SQLite fixtures only."""
import importlib.util
import os
from pathlib import Path
import sqlite3
from contextlib import closing
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bin'))
import webui


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {'HOME': str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.stopped = mock.patch.object(webui, 'require_stopped')
        self.stopped.start()
        self.addCleanup(self.stopped.stop)

    def account(self, role='admin'):
        data = Path(webui.prefix()) / 'data'
        data.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(data / 'webui.db')) as db:
            db.execute('CREATE TABLE "user" (role TEXT)')
            db.execute('INSERT INTO "user" VALUES (?)', (role,))
            db.commit()

    def test_new_profile_defaults_to_loopback_and_private_env(self):
        webui.write_env()
        self.assertIn('HOST=127.0.0.1\n', Path(webui.env_path()).read_text())
        self.assertEqual(Path(webui.env_path()).stat().st_mode & 0o777, 0o600)
        self.assertEqual(webui.access_settings()['access'], 'local')

    def test_network_requires_existing_admin_and_never_creates_database(self):
        webui.write_env()
        for confirm in (False, True):
            result = webui.set_access('network', confirm)
            self.assertFalse(result['success'])
            self.assertNotIn('needs_confirm', result)
            self.assertIn('administrator', result['error'])
        self.assertFalse((Path(webui.prefix()) / 'data/webui.db').exists())
        self.assertIn('HOST=127.0.0.1', Path(webui.env_path()).read_text())

    def test_regular_user_is_not_enough_for_network_access(self):
        webui.write_env()
        self.account('user')
        self.assertFalse(webui.set_access('network', True)['success'])

    def test_network_change_confirms_then_preserves_secret_and_requires_stopped_service(self):
        webui.write_env()
        self.account()
        before = Path(webui.env_path()).read_text()
        with mock.patch.object(webui, 'require_stopped'):
            result = webui.set_access('network', False)
            self.assertTrue(result['needs_confirm'])
            self.assertEqual(Path(webui.env_path()).read_text(), before)
            with mock.patch.object(webui, 'systemctl') as calls:
                result = webui.set_access('network', True)
                calls.assert_not_called()
            self.assertTrue(result['success'])
        after = Path(webui.env_path()).read_text()
        self.assertEqual(after, before.replace('HOST=127.0.0.1', 'HOST=0.0.0.0'))
        self.assertEqual(webui.access_settings()['access'], 'network')

    def test_running_service_cannot_change_access(self):
        webui.write_env()
        self.account()
        before = Path(webui.env_path()).read_bytes()
        with mock.patch.object(webui, 'require_stopped', side_effect=ValueError('Stop Open WebUI first.')):
            self.assertFalse(webui.set_access('network', True)['success'])
        self.assertEqual(Path(webui.env_path()).read_bytes(), before)

    def test_local_access_can_recover_missing_or_corrupt_database(self):
        webui.write_env()
        path = Path(webui.env_path())
        path.write_text(path.read_text().replace('HOST=127.0.0.1', 'HOST=0.0.0.0'))
        with mock.patch.object(webui, 'require_stopped'):
            self.assertTrue(webui.set_access('local', True)['success'])
        self.assertIn('HOST=127.0.0.1', path.read_text())

    def test_existing_network_configuration_cannot_start_without_account(self):
        webui.write_env()
        path = Path(webui.env_path())
        path.write_text(path.read_text().replace('HOST=127.0.0.1', 'HOST=0.0.0.0'))
        with mock.patch.object(webui, 'port_open', return_value=False), \
             mock.patch.object(os, 'access', return_value=True), \
             mock.patch.object(webui, 'systemctl') as calls:
            result = webui.start()
        self.assertFalse(result['success'])
        self.assertIn('administrator', result['error'])
        calls.assert_not_called()

    def test_indented_host_changes_once_and_reads_back(self):
        webui.write_env()
        path = Path(webui.env_path())
        path.write_text(path.read_text().replace('HOST=127.0.0.1', '  export HOST=0.0.0.0'))
        result = webui.set_access('local', True)
        self.assertTrue(result['success'])
        self.assertEqual(sum('HOST=' in line for line in path.read_text().splitlines()), 1)
        self.assertEqual(webui.access_settings()['access'], 'local')

    def test_network_refuses_custom_or_redirected_database(self):
        webui.write_env()
        self.account()
        config = dict(webui.access_config(), HOST='0.0.0.0')
        with self.assertRaisesRegex(ValueError, 'custom DATABASE_URL'):
            webui.check_network_access(dict(config, DATABASE_URL='postgresql://fixture.invalid/test'))
        database = Path(webui.prefix()) / 'data/webui.db'
        other = self.home / 'other.db'
        database.rename(other)
        database.symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'redirected'):
            webui.check_network_access(config)

    def test_network_guard_timeout_returns_failure_without_writing(self):
        webui.write_env()
        before = Path(webui.env_path()).read_bytes()
        with mock.patch.object(webui.subprocess, 'run', side_effect=subprocess.TimeoutExpired('guard', 5)):
            result = webui.set_access('network', True)
        self.assertFalse(result['success'])
        self.assertEqual(Path(webui.env_path()).read_bytes(), before)

    def test_wrapper_enforces_guard_before_exec_even_when_started_directly(self):
        webui.write_env()
        webui.write_wrapper()
        binary = Path(webui.webui_bin())
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\nprintf reached-cli\n')
        binary.chmod(0o755)
        path = Path(webui.env_path())
        path.write_text(path.read_text().replace('HOST=127.0.0.1', 'HOST=0.0.0.0'))
        result = subprocess.run([webui.wrapper_path()], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('reached-cli', result.stdout)
        self.assertIn('administrator', result.stderr)
        self.account()
        result = subprocess.run([webui.wrapper_path()], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('reached-cli', result.stdout)


if __name__ == '__main__':
    unittest.main()
