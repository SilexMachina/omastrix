"""Fresh WebUI service discovery: distinguish missing units from broken probes."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bin'))
import webui


class FreshWebuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = mock.patch.dict(os.environ, {'HOME': self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)

    @staticmethod
    def missing(*args):
        if args[0] == 'is-active':
            return 4, 'inactive'
        if args[0] == 'show':
            return 0, 'LoadState=not-found\nActiveState=inactive'
        raise AssertionError('Unexpected service operation: ' + args[0])

    def test_confirmed_missing_unit_is_installable(self):
        with mock.patch.object(webui, 'systemctl', side_effect=self.missing):
            info = webui.status()
        self.assertFalse(info['installed'])
        self.assertEqual(info['state'], 'not_installed')

    def test_confirmed_missing_unit_is_safe_for_first_install_worker(self):
        with mock.patch.object(webui, 'systemctl', side_effect=self.missing):
            webui.require_stopped()

    def test_probe_errors_and_ambiguous_missing_unit_never_enable_install(self):
        for first, second in [
            ((1, 'inactive'), (0, 'LoadState=not-found\nActiveState=inactive')),
            ((4, 'inactive'), (1, 'LoadState=not-found\nActiveState=inactive')),
            ((4, 'inactive'), (0, 'LoadState=loaded\nActiveState=active')),
            ((4, 'inactive'), (0, 'LoadState=not-found\nActiveState=inactive\nActiveState=active')),
            ((4, 'unknown'), (0, '')),
        ]:
            def service(*args):
                return first if args[0] == 'is-active' else second
            with self.subTest(first=first, second=second), mock.patch.object(webui, 'systemctl', side_effect=service):
                self.assertEqual(webui.status()['state'], 'unavailable')
                with self.assertRaises(ValueError):
                    webui.require_stopped()


if __name__ == '__main__':
    unittest.main()
