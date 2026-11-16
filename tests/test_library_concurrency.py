"""Independent model operations and shared file exclusion."""
import copy
import subprocess
from pathlib import Path
from unittest import mock
from test_backend_safety import IsolatedBackend, library


class MutationTests(IsolatedBackend):
    def setUp(self):
        super().setUp()
        self.other = copy.deepcopy(self.row)
        self.other['id'] = 'other-model'
        self.other['name'] = 'Other model'
        self.other['files'][0]['path'] = 'other/model.gguf'
        patcher = mock.patch.object(library, 'all_models', return_value=([self.row, self.other], 14))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_model_root_stays_with_file_locks_when_link_changes(self):
        import fcntl
        root_a, root_b = self.home / 'root-a', self.home / 'root-b'
        for root in (root_a, root_b):
            path = root / self.row['files'][0]['path']
            path.parent.mkdir(parents=True)
            path.write_bytes(b'GGUF')
        link = self.home / 'models'
        link.symlink_to(root_a, target_is_directory=True)
        flock = fcntl.flock
        switched = []
        def lock_and_switch(lock, operation):
            result = flock(lock, operation)
            if 'file-' in lock.name and operation != fcntl.LOCK_UN and not switched:
                link.unlink()
                link.symlink_to(root_b, target_is_directory=True)
                switched.append(True)
            return result
        @library.model_mutation()
        def operation(model_id):
            path = library.dest_for(self.row['files'][0]['path'])
            library.write_preset(110)
            library.remove_catalog_file(path)
            return path
        with mock.patch.object(library.fcntl, 'flock', side_effect=lock_and_switch), \
             mock.patch.object(library, 'server_list', return_value={}):
            result = operation(self.row['id'])
        self.assertEqual(result, str(root_a / self.row['files'][0]['path']))
        self.assertFalse((root_a / self.row['files'][0]['path']).exists())
        self.assertTrue((root_b / self.row['files'][0]['path']).exists())
        self.assertIn('model = ' + str(root_a), Path(library.preset_path()).read_text())
        self.assertEqual(library.dest_for(self.row['files'][0]['path']),
                         str(root_b / self.row['files'][0]['path']))

    def test_preset_root_is_resolved_once_per_write(self):
        root_a, root_b = self.home / 'root-a', self.home / 'root-b'
        path = root_a / self.row['files'][0]['path']
        path.parent.mkdir(parents=True)
        path.write_bytes(b'GGUF')
        root_b.mkdir()
        link = self.home / 'models'
        link.symlink_to(root_a, target_is_directory=True)
        row_files = library.row_files
        def inspect_and_switch(row):
            result = row_files(row)
            link.unlink()
            link.symlink_to(root_b, target_is_directory=True)
            return result
        with mock.patch.object(library, 'row_files', side_effect=inspect_and_switch), \
             mock.patch.object(library, 'server_list', return_value={}):
            library.write_preset(110)
        self.assertIn('model = ' + str(path), Path(library.preset_path()).read_text())
        with mock.patch.object(library, 'server_list', return_value={}):
            library.write_preset(110)
        self.assertNotIn('[test-model]', Path(library.preset_path()).read_text())

    def test_download_allows_other_load_delete_and_download(self):
        other_path = Path(library.dest_for(self.other['files'][0]['path']))
        other_path.parent.mkdir(parents=True)
        other_path.write_bytes(b'GGUF')
        results = []
        def transfer(cmd, **kwargs):
            results.append(library.load_checked(self.other['id'], 110, False))
            results.append(library.delete_model(self.other['id'], 110, True))
            results.append(library.start_download(self.other['id']))
            Path(cmd[cmd.index('-o') + 1]).write_bytes(b'GGUF')
            return subprocess.CompletedProcess(cmd, 0)
        with mock.patch.object(library, 'server_list', return_value={self.other['id']: 'loaded'}), \
             mock.patch.object(library, 'unload_name', return_value={}), \
             mock.patch.object(library, 'wait_unloaded', return_value=True), \
             mock.patch.object(library, 'write_preset'), \
             mock.patch('subprocess.Popen', return_value=mock.Mock(pid=12345)), \
             mock.patch('subprocess.run', side_effect=transfer), self.quiet():
            self.assertEqual(library.fetch(self.row['id']), 0)
        self.assertTrue(all(result['success'] for result in results), results)

    def test_shared_files_loaded_under_another_id_are_not_mutated(self):
        self.other['files'][0]['path'] = self.row['files'][0]['path']
        path = self.file()
        with mock.patch.object(library, 'server_list', return_value={self.other['id']: 'loaded'}), \
             mock.patch.object(library, 'write_preset'), self.quiet():
            self.assertEqual(library.fetch(self.row['id']), 1)
            self.assertFalse(library.delete_model(self.row['id'], 110, True)['success'])
        self.assertEqual(path.read_bytes(), b'GGUF')

    def test_duplicate_worker_rejects_busy_model_without_waiting(self):
        import fcntl
        import threading
        self.file()
        lock = self.home / ('.local/state/omastrix/downloads-' + self.row['id'] + '.lock')
        lock.parent.mkdir(parents=True)
        results = []
        with lock.open('a') as held, self.quiet():
            fcntl.flock(held, fcntl.LOCK_EX)
            worker = threading.Thread(target=lambda: results.append(library.verify(self.row['id'])))
            worker.start()
            worker.join(0.2)
            completed = not worker.is_alive()
            fcntl.flock(held, fcntl.LOCK_UN)
            worker.join(2)
        self.assertTrue(completed)
        self.assertEqual(results, [1])

    def test_shared_filename_download_is_excluded(self):
        self.other['files'][0]['path'] = self.row['files'][0]['path']
        results = []
        def transfer(cmd, **kwargs):
            results.append(library.start_download(self.other['id']))
            Path(cmd[cmd.index('-o') + 1]).write_bytes(b'GGUF')
            return subprocess.CompletedProcess(cmd, 0)
        with mock.patch.object(library, 'server_list', return_value={}), \
             mock.patch('subprocess.run', side_effect=transfer), self.quiet():
            self.assertEqual(library.fetch(self.row['id']), 0)
        self.assertFalse(results[0]['success'])
