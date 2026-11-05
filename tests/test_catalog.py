"""Shipped recipes must remain reproducible and make sourced claims."""
import json
from pathlib import Path, PurePosixPath
import re
import unittest
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def test_files_are_revision_pinned(self):
        catalog = json.loads((ROOT / 'catalog.json').read_text())
        for model in catalog['models']:
            with self.subTest(model=model['id']):
                revision = model.get('revision', '')
                self.assertRegex(revision, r'^[0-9a-f]{40}$')
                for file in model['files']:
                    self.assertIn('/resolve/' + revision + '/', file['url'])

    def test_parameter_counts_are_sourced_at_the_pinned_revision(self):
        catalog = json.loads((ROOT / 'catalog.json').read_text())
        for model in catalog['models']:
            with self.subTest(model=model['id']):
                self.assertIs(type(model.get('parameter_count')), int)
                self.assertGreater(model['parameter_count'], 0)
                url = urlparse(model['files'][0]['url'])
                owner, repo = url.path.strip('/').split('/')[:2]
                expected = f'https://huggingface.co/api/models/{owner}/{repo}/revision/{model["revision"]}'
                self.assertEqual(model.get('metadata_source'), expected)

    def test_speed_claims_have_reproducible_measurements(self):
        catalog = json.loads((ROOT / 'catalog.json').read_text())
        for model in catalog['models']:
            if 'speed' in model:
                for field in ('machine', 'context', 'date', 'engine_commit', 'backend'):
                    self.assertTrue(model['speed'].get(field), (model['id'], field))

    def test_performance_labels_require_benchmark_evidence(self):
        catalog = json.loads((ROOT / 'catalog.json').read_text())
        for model in catalog['models']:
            with self.subTest(model=model['id']):
                if any(tag.casefold() in ('fast', 'fastest') for tag in model['tags']):
                    self.assertIn('speed', model, 'Performance labels need reproducible measurements')

    def test_file_integrity_and_relative_paths(self):
        catalog = json.loads((ROOT / 'catalog.json').read_text())
        ids = set()
        for model in catalog['models']:
            self.assertNotIn(model['id'], ids)
            ids.add(model['id'])
            self.assertEqual(sum(file.get('primary', False) for file in model['files']), 1)
            for file in model['files']:
                path = PurePosixPath(file['path'])
                self.assertFalse(path.is_absolute())
                self.assertNotIn('..', path.parts)
                self.assertEqual(urlparse(file['url']).scheme, 'https')
                self.assertRegex(file['sha256'], r'^[0-9a-f]{64}$')
                self.assertGreater(file['bytes'], 0)
