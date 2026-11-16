"""Verified file identity and memory budget contracts."""
import os
from pathlib import Path
from unittest import mock
from test_backend_safety import IsolatedBackend, library


class BudgetTests(IsolatedBackend):
    def test_desktop_reserve_stays_outside_gtt(self):
        self.row['kv_gib'] = 100
        self.file()
        with mock.patch.object(library, 'server_list', return_value={self.row['id']: 'loaded'}), \
             mock.patch.object(library, 'slot_state', return_value=False), \
             mock.patch.object(library, 'service_ram_gb', return_value=None):
            self.assertTrue(library.library_view(110)['rows'][0]['fits'])
            self.assertIn('[test-model]', library.preset_text(110))
            self.assertTrue(library.load_checked(self.row['id'], 110, False)['success'])

    def test_unknown_budget_is_not_published_as_loadable(self):
        self.file()
        with mock.patch.object(library, 'server_list', return_value={}):
            self.assertNotIn('[test-model]', library.preset_text(None))

    def test_physical_memory_caps_budget_after_reserve(self):
        with mock.patch.object(library, 'physical_ram_gib', return_value=64):
            self.assertEqual(library.model_budget(96, 14), 50)
            self.assertEqual(library.model_budget(32, 14), 32)
            self.assertIsNone(library.model_budget(None, 14))


class VerificationTests(IsolatedBackend):
    def test_explicit_verify_rehashes_without_downloading(self):
        self.file()
        with mock.patch.object(library, 'server_list', return_value={}), \
             mock.patch.object(library, 'sha256_file', wraps=library.sha256_file) as digest, self.quiet():
            self.assertEqual(library.verify(self.row['id']), 0)
            self.assertEqual(library.verify(self.row['id']), 0)
        self.assertEqual(digest.call_count, 2)

    def test_verify_launcher_uses_dedicated_worker_verb(self):
        with mock.patch('subprocess.Popen', return_value=mock.Mock(pid=12345)) as spawn:
            result = library.start_verify(self.row['id'])
        self.assertTrue(result['success'])
        self.assertEqual(spawn.call_args.args[0][1:], ['library-verify-run', self.row['id']])

    def test_fetch_records_identity_and_recovers_oversized_partial(self):
        path = Path(library.dest_for(self.row['files'][0]['path'] + '.part'))
        path.parent.mkdir(parents=True)
        path.write_bytes(b'oversized partial')
        def transfer(cmd, **kwargs):
            self.assertFalse(path.exists())
            path.write_bytes(b'GGUF')
            return library.subprocess.CompletedProcess(cmd, 0)
        with mock.patch.object(library, 'server_list', return_value={}), \
             mock.patch('subprocess.run', side_effect=transfer), self.quiet():
            self.assertEqual(library.fetch(self.row['id']), 0)
        item = self.row['files'][0]
        dest = library.dest_for(item['path'])
        self.assertEqual(library.read_verified()[dest], dict(library.file_identity(dest), sha256=item['sha256']))
        with mock.patch.object(library, 'sha256_file', side_effect=AssertionError('unchanged file was hashed')):
            self.assertTrue(library.verify_file(item))

    def test_second_load_uses_verified_identity_and_touch_rehashes(self):
        path = self.file()
        with mock.patch.object(library, 'server_list', return_value={self.row['id']: 'loaded'}), \
             mock.patch.object(library, 'sha256_file', wraps=library.sha256_file) as digest:
            self.assertTrue(library.load_checked(self.row['id'], 110, False)['success'])
            self.assertTrue(library.load_checked(self.row['id'], 110, False)['success'])
            self.assertEqual(digest.call_count, 1)
            stamp = path.stat()
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1))
            self.assertTrue(library.load_checked(self.row['id'], 110, False)['success'])
            self.assertEqual(digest.call_count, 2)

    def test_modification_during_hash_does_not_publish_verified_identity(self):
        path = self.file()
        digest = library.sha256_file
        def change(candidate):
            result = digest(candidate)
            Path(candidate).write_bytes(b'BAD!')
            return result
        with mock.patch.object(library, 'sha256_file', side_effect=change), \
             mock.patch.object(library, 'server_list', return_value={}) as router:
            result = library.load_checked(self.row['id'], 110, False)
        self.assertFalse(result['success'])
        router.assert_not_called()
        with mock.patch.object(library, 'server_list', return_value={}):
            self.assertFalse(library.load_checked(self.row['id'], 110, False)['success'])

    def test_ctime_detects_same_size_edit_with_restored_mtime(self):
        path = self.file()
        item = self.row['files'][0]
        self.assertTrue(library.verify_file(item))
        stamp = path.stat()
        path.write_bytes(b'BAD!')
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertFalse(library.verify_file(item))

    def test_fetch_rejects_file_changed_during_hash(self):
        self.file()
        digest = library.sha256_file
        def change(candidate):
            result = digest(candidate)
            Path(candidate).write_bytes(b'BAD!')
            return result
        with mock.patch.object(library, 'server_list', return_value={}), \
             mock.patch.object(library, 'sha256_file', side_effect=change), self.quiet():
            self.assertEqual(library.fetch(self.row['id']), 1)
        self.assertEqual(library.read_verified(), {})

    def test_partial_changed_during_publication_is_not_cached(self):
        partial = Path(library.dest_for(self.row['files'][0]['path'] + '.part'))
        partial.parent.mkdir(parents=True)
        partial.write_bytes(b'GGUF')
        replace = os.replace
        def mutate_and_publish(source, destination, **kwargs):
            if source == str(partial):
                stamp = partial.stat()
                partial.write_bytes(b'BAD!')
                os.utime(partial, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            return replace(source, destination, **kwargs)
        with mock.patch.object(library.os, 'replace', side_effect=mutate_and_publish), \
             mock.patch.object(library, 'server_list', return_value={}), self.quiet():
            self.assertEqual(library.fetch(self.row['id']), 1)
        self.assertEqual(library.read_verified(), {})

    def test_changed_expected_hash_never_uses_old_cache(self):
        self.file()
        with mock.patch.object(library, 'server_list', return_value={self.row['id']: 'loaded'}):
            self.assertTrue(library.load_checked(self.row['id'], 110, False)['success'])
            self.row['files'][0]['sha256'] = '0' * 64
            self.assertFalse(library.load_checked(self.row['id'], 110, False)['success'])
