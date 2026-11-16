"""Storage layout and preset publication contracts."""
from pathlib import Path
from unittest import mock
from test_backend_safety import IsolatedBackend, library


class LayoutTests(IsolatedBackend):
    def test_download_rejects_invalid_id_as_action_error(self):
        result = library.start_download('../outside')
        self.assertFalse(result['success'])

    def test_added_metadata_does_not_follow_product_file_links(self):
        outside = self.home / 'outside.json'
        outside.write_text('{"models": [{"id": "outside"}]}')
        path = Path(library.added_path())
        path.parent.mkdir(parents=True)
        path.symlink_to(outside)
        with self.assertRaises(ValueError):
            library.load_added()

    def test_download_state_does_not_follow_file_links(self):
        outside = self.home / 'outside-state.json'
        outside.write_text('{"pid": 0}')
        path = Path(library.download_path(self.row['id']))
        path.symlink_to(outside)
        with self.assertRaises(ValueError):
            library.download_state(self.row['id'])

    def test_model_query_quotes_slash(self):
        with mock.patch.object(library, 'http_json', return_value=[]) as request:
            library.slot_state('one/two')
        self.assertIn('model=one%2Ftwo', request.call_args.args[0])

    def test_recommendation_accepts_catalog_absence(self):
        self.assertIsNone(library.recommend_id([]))
        self.assertEqual(library.recommend_id([{'id': 'one', 'fits': True}]), 'one')

    def test_library_view_has_no_unused_token_metrics(self):
        self.file()
        with mock.patch.object(library, 'server_list', return_value={self.row['id']: 'loaded'}), \
             mock.patch.object(library, 'slot_state', return_value=False), \
             mock.patch.object(library, 'service_ram_gb', return_value=None):
            view = library.library_view(110)
        self.assertNotIn('tokens_since_load', view)
        self.assertFalse(hasattr(library, 'token_count'))

    def test_models_root_link_is_resolved_at_each_operation(self):
        target = self.home / 'disk'
        target.mkdir()
        (self.home / 'models').symlink_to(target, target_is_directory=True)
        self.assertEqual(library.dest_for('one/model.gguf'), str(target / 'one/model.gguf'))

    def test_trusted_config_link_allows_product_writes(self):
        target = self.home / 'config-store'
        target.mkdir()
        (self.home / '.config').symlink_to(target, target_is_directory=True)
        path = self.home / '.config/omastrix/models.ini'
        self.assertEqual(library.checked_app_path(str(path)), str(target / 'omastrix/models.ini'))
        library.atomic_text(str(path), 'complete', reject_symlink=True)
        self.assertEqual(path.read_text(), 'complete')

    def test_product_root_and_descendant_links_are_rejected(self):
        target = self.home / 'outside'
        target.mkdir()
        root = self.home / '.config/omastrix'
        root.parent.mkdir()
        root.symlink_to(target)
        with self.assertRaises(ValueError):
            library.checked_app_path(str(root / 'models.ini'))

    def test_fresh_preset_has_only_canonical_section(self):
        self.file()
        with mock.patch.object(library, 'server_list', return_value={}):
            text = library.preset_text(110)
        self.assertIn('[test-model]', text)
        self.assertNotIn('[Test model]', text)

    def test_unloaded_preexisting_alias_is_not_emitted(self):
        path = self.file()
        preset = Path(library.preset_path())
        preset.parent.mkdir(parents=True)
        preset.write_text('[Test model]\nmodel = ' + str(path) + '\n')
        with mock.patch.object(library, 'server_list', return_value={'Test model': 'unloaded'}):
            self.assertNotIn('[Test model]', library.preset_text(110))

    def test_loaded_alias_requires_matching_saved_model_path(self):
        self.file()
        preset = Path(library.preset_path())
        preset.parent.mkdir(parents=True)
        preset.write_text('[Test model]\nmodel = /different/model.gguf\n')
        with mock.patch.object(library, 'server_list', return_value={'Test model': 'loaded'}):
            self.assertNotIn('[Test model]', library.preset_text(110))

    def test_loaded_alias_survives_unavailable_memory_budget(self):
        model = self.file()
        preset = Path(library.preset_path())
        preset.parent.mkdir(parents=True)
        preset.write_text('[Test model]\nmodel = ' + str(model) + '\n')
        with mock.patch.object(library, 'server_list', return_value={'Test model': 'loaded'}):
            text = library.preset_text(None)
        self.assertIn('[Test model]', text)
        self.assertNotIn('[test-model]', text)

    def test_unchanged_preset_does_not_publish_again(self):
        with mock.patch.object(library, 'server_list', return_value={}):
            library.write_preset(110)
            with mock.patch.object(library, 'atomic_text') as publish:
                library.write_preset(110)
        publish.assert_not_called()
