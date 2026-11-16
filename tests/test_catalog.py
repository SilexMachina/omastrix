"""Shipped recipes must remain reproducible and make sourced claims."""
import json
from pathlib import Path, PurePosixPath
import re
import unittest
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def public_hardware_description(value):
    """Require a hardware description, excluding obvious machine identifiers.

    This is a publication guard, not proof that arbitrary free text is anonymous.
    CPU/GPU product names and memory capacities remain useful benchmark metadata.
    """
    if not isinstance(value, str) or not value.strip():
        return False
    if re.search(r'(?:^|[\s=;])(?:~?/\S|[a-z]:[\\/])|\\\\|\b(?:host(?:name)?|machine|node)\s*[:=]', value, re.I):
        return False
    # Qualified hostnames and IP literals are not hardware specs; decimal
    # clock speeds and interface versions (3.5 GHz, PCIe 4.0) are valid.
    if re.search(r'\b[\w-]+(?:\.[\w-]+)*\.[a-z][a-z0-9-]*\b|\b(?:\d{1,3}\.){3}\d{1,3}\b|(?:[0-9a-f]*:){2,}[0-9a-f:]+', value, re.I):
        return False
    # Bare host labels are not reproducible hardware descriptions. Avoid a
    # vendor/model allowlist so new CPU and GPU families remain acceptable.
    return bool(re.search(r'\s', value.strip()) and re.search(r'[A-Za-z]', value))


class HardwareDescriptionTests(unittest.TestCase):
    def test_rejects_host_identifiers_and_private_locations(self):
        for value in (
            'bench-node-07', 'bench-node-07.local; 128 GiB RAM',
            '128 GiB RAM; hostname=bench-node-07',
            '128 GiB RAM; /home/example/models',
            '128 GiB RAM; ~/models', '128 GiB RAM; C:\\Users\\Example',
            '128 GiB RAM; 192.0.2.17', '128 GiB RAM; 2001:db8::17',
            '128 GiB RAM; 10.23.45.67',
        ):
            with self.subTest(value=value):
                self.assertFalse(public_hardware_description(value))

    def test_accepts_reproducible_hardware_descriptions(self):
        for value in (
            'ExampleVendor CPU Model 123; ExampleGPU Model 456; 64 GiB RAM',
            'Example CPU 8-core; Example GPU 24 GB; 64 GB RAM',
            'Example SoC Model 5; 32 GB unified memory',
            'ExampleVendor Graphics Model 789',
            '8-core CPU at 3.5 GHz; 32 GiB RAM; PCIe 4.0',
            'Example GPU / 16 GiB VRAM',
        ):
            with self.subTest(value=value):
                self.assertTrue(public_hardware_description(value))


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
                self.assertTrue(
                    public_hardware_description(model['speed']['machine']),
                    'speed.machine must describe hardware, not a hostname, path or IP address',
                )

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
