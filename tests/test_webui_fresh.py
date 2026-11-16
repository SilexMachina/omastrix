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

    def test_confirmed_update_passes_approval_to_detached_worker(self):
        with mock.patch.object(webui, 'status', return_value={'state': 'stopped'}), \
             mock.patch.object(webui, 'latest_release', return_value=('0.14.0', '')), \
             mock.patch.object(webui, 'version_of', return_value='0.13.0'), \
             mock.patch.object(webui, 'find_uv', return_value=''), \
             mock.patch.object(webui.dependencies, 'install') as install, \
             mock.patch.object(webui.subprocess, 'Popen', return_value=mock.Mock(pid=123456)) as spawn:
            result = webui.start_update(confirm=True)
            self.assertTrue(result['success'])
            self.assertEqual(spawn.call_args.args[0][-3:], ['webui-update-run', '0.14.0', '--confirm'])
            self.assertTrue(spawn.call_args.kwargs['start_new_session'])
            install.assert_not_called()

    def test_missing_distribution_metadata_never_starts_python(self):
        venv = Path(self.temp.name) / '.local/share/omastrix/webui/venvs' / ('b' * 32)
        (venv / 'bin').mkdir(parents=True)
        python = venv / 'bin/python'
        python.write_text('fake interpreter')
        python.chmod(0o755)
        with mock.patch.object(webui.subprocess, 'run', side_effect=AssertionError('no interpreter startup')):
            self.assertEqual(webui.version_of(str(venv / 'bin/open-webui')), '')

    def test_distribution_metadata_cache_tracks_replacement_without_python(self):
        venv = Path(self.temp.name) / '.local/share/omastrix/webui/venvs' / ('a' * 32)
        (venv / 'bin').mkdir(parents=True)
        python = venv / 'bin/python'
        python.write_text('fake interpreter')
        python.chmod(0o755)
        metadata = venv / 'lib/python3.11/site-packages/open_webui-0.13.0.dist-info/METADATA'
        metadata.parent.mkdir(parents=True)
        metadata.write_text('Name: open-webui\nVersion: 0.13.0\n')
        with mock.patch.object(webui.subprocess, 'run', side_effect=AssertionError('no interpreter startup')):
            self.assertEqual(webui.version_of(str(venv / 'bin/open-webui')), '0.13.0')
            self.assertEqual(webui.version_of(str(venv / 'bin/open-webui')), '0.13.0')
            metadata.write_text('Name: open-webui\nVersion: 0.14.0\n')
            self.assertEqual(webui.version_of(str(venv / 'bin/open-webui')), '0.14.0')

    def test_safe_path_allows_user_managed_prefix_links_but_not_app_links(self):
        target = Path(self.temp.name) / 'settings'
        target.mkdir()
        (Path(self.temp.name) / '.config').symlink_to(target, target_is_directory=True)
        candidate = Path(self.temp.name) / '.config/omastrix/webui.env'
        self.assertEqual(webui.safe_path(str(candidate)), str(target / 'omastrix/webui.env'))
        (target / 'omastrix').symlink_to(target / 'other', target_is_directory=True)
        with self.assertRaises(ValueError):
            webui.safe_path(str(candidate))

    def test_open_file_reference_protects_a_running_version(self):
        proc = Path(self.temp.name) / 'proc'
        process = proc / '123'
        (process / 'fd').mkdir(parents=True)
        for name in ('cmdline', 'environ', 'maps'):
            (process / name).write_bytes(b'')
        old = Path(self.temp.name) / 'old-version'
        old.mkdir()
        (process / 'fd/7').symlink_to(old / 'model')
        with mock.patch.object(webui, 'PROC_ROOT', str(proc)):
            self.assertTrue(webui.versions_in_use([str(old)]))

    def test_other_user_process_reference_also_blocks_pruning(self):
        proc = Path(self.temp.name) / 'proc'
        process = proc / '123'
        (process / 'fd').mkdir(parents=True)
        old = Path(self.temp.name) / 'old-version'
        old.mkdir()
        (process / 'environ').write_bytes(os.fsencode(str(old)))
        for name in ('cmdline', 'maps'):
            (process / name).write_bytes(b'')
        with mock.patch.object(webui, 'PROC_ROOT', str(proc)), mock.patch.object(os, 'getuid', return_value=-1):
            self.assertTrue(webui.versions_in_use([str(old)]))

    def test_pruning_cannot_follow_a_managed_root_swapped_for_a_symlink(self):
        import shutil
        root = Path(webui.prefix()) / 'venvs'
        old = root / ('a' * 32)
        old.mkdir(parents=True)
        (old / 'sentinel').write_text('keep external copy')
        marker = '.omastrix-tree.json'
        webui.library.atomic_json(str(old / marker), webui.tree_identity(str(old), marker))
        external = Path(self.temp.name) / 'unrelated'
        shutil.copytree(root, external)
        saved = root.with_name('saved')
        def swap(paths):
            root.rename(saved)
            root.symlink_to(external, target_is_directory=True)
            return False
        with mock.patch.object(webui, 'versions_in_use', side_effect=swap), mock.patch.object(webui, 'require_stopped'):
            webui.prune_venvs(str(root / ('b' * 32)), None)
        self.assertEqual((external / old.name / 'sentinel').read_text(), 'keep external copy')

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
