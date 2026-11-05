"""Offline release metadata tests; no services, downloads, tags, or publishing."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "release.py"


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="omastrix-release-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "manifest.json").write_text(json.dumps({"id": "example", "version": "0.4.0-dev.1"}) + "\n")
        (self.root / "CHANGELOG.md").write_text("# Changelog\n\n## [0.4.0-dev.1] - Unreleased\n\n- Existing work.\n")

    def run_tool(self, *args):
        return subprocess.run([sys.executable, str(TOOL), "--root", str(self.root), *args], capture_output=True, text=True)

    def test_check_validates_manifest_and_changelog_without_writes(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        result = self.run_tool("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0.4.0-dev.1", result.stdout)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_check_rejects_invalid_semver(self):
        for version in ["v0.4.0", "0.4", "01.4.0", "0.4.0-dev.01", "0.4.0-", "0.4.0+", "0.4.0\n", 4, None]:
            with self.subTest(version=version):
                (self.root / "manifest.json").write_text(json.dumps({"version": version}))
                result = self.run_tool("check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("SemVer", result.stderr)

    def test_check_rejects_missing_stale_duplicate_and_empty_notes(self):
        for text in ["# Changelog\n", "## [0.3.0] - Unreleased\n- Old\n", "## [0.4.0-dev.1] - Unreleased\n- One\n## [0.4.0-dev.1] - Unreleased\n- Two\n", "## [0.4.0-dev.1] - Unreleased\n"]:
            (self.root / "CHANGELOG.md").write_text(text)
            result = self.run_tool("check")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("changelog", result.stderr)

    def test_check_rejects_malformed_sections_instead_of_ignoring_them(self):
        current = (self.root / "CHANGELOG.md").read_text()
        manifest = (self.root / "manifest.json").read_text()
        for heading in ("## [0.5.0]", "## [0.3.0] -", "## [not-semver] - Unreleased"):
            with self.subTest(heading=heading):
                (self.root / "manifest.json").write_text(manifest)
                (self.root / "CHANGELOG.md").write_text(current + "\n" + heading + "\n\n- Older note.\n")
                before = {p.name: p.read_bytes() for p in self.root.iterdir()}
                result = self.run_tool("bump", "0.4.0-dev.2", "--note", "Next change.", "--write")
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("changelog", result.stderr)
                self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_missing_or_malformed_files_report_error_without_traceback(self):
        (self.root / "manifest.json").write_text("{")
        result = self.run_tool("check")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        (self.root / "manifest.json").unlink()
        result = self.run_tool("check")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)

    def test_version_reads_single_source_from_any_cwd(self):
        result = self.run_tool("version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0.4.0-dev.1")

    def test_bump_previews_by_default_then_writes_only_metadata(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        result = self.run_tool("bump", "0.4.0-dev.2", "--note", "Improve controls.")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dry run", result.stdout)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        result = self.run_tool("bump", "0.4.0-dev.2", "--note", "Improve controls.", "--write")
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.root / "manifest.json").read_text())
        self.assertEqual(manifest, {"id": "example", "version": "0.4.0-dev.2"})
        notes = (self.root / "CHANGELOG.md").read_text()
        self.assertIn("## [0.4.0-dev.2] - Unreleased\n\n- Improve controls.", notes)
        self.assertIn("## [0.4.0-dev.1] - Unreleased\n\n- Existing work.", notes)
        self.assertEqual(self.run_tool("check").returncode, 0)
        self.assertEqual(set(before), {p.name for p in self.root.iterdir()})

    def test_bump_requires_note_and_rejects_multiline_or_empty_notes(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        for extra in [[], ["--note", ""], ["--note", "   "], ["--note", "One\n## Forged release"]]:
            result = self.run_tool("bump", "0.4.0-dev.2", "--write", *extra)
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_bump_rejects_unicode_line_separators_without_writes(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        for separator in ('\v', '\f', '\x1c', '\x1d', '\x1e', '\x85', '\u2028', '\u2029'):
            with self.subTest(separator=repr(separator)):
                for name, content in before.items():
                    (self.root / name).write_bytes(content)
                result = self.run_tool("bump", "0.4.0-dev.2", "--note", "One" + separator + "Two", "--write")
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_bump_enforces_semver_precedence_not_string_order(self):
        for target in ["0.4.0-dev.0", "0.4.0-dev.1", "0.4.0-dev.1+build", "0.3.9", "v0.5.0", "0.4.0-dev.02"]:
            before = {p.name: p.read_bytes() for p in self.root.iterdir()}
            result = self.run_tool("bump", target, "--note", "A change.", "--write")
            self.assertNotEqual(result.returncode, 0, target)
            self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        for target in ["0.4.0-dev.10", "0.4.0-rc.1", "0.4.0", "0.5.0-dev.1", "0.5.0"]:
            result = self.run_tool("bump", target, "--note", "A change.")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_stable_version_sorts_after_prereleases(self):
        (self.root / "manifest.json").write_text(json.dumps({"version": "0.5.0"}))
        (self.root / "CHANGELOG.md").write_text("## [0.5.0] - Unreleased\n\n- Candidate only.\n")
        for target in ["0.5.0-rc.1", "0.5.0+meta"]:
            self.assertNotEqual(self.run_tool("bump", target, "--note", "A change.").returncode, 0)
        self.assertEqual(self.run_tool("bump", "0.5.1-dev.1", "--note", "A change.").returncode, 0)

    def test_dated_release_section_allows_validation_and_next_dev_bump(self):
        (self.root / "CHANGELOG.md").write_text("## [0.4.0-dev.1] - 2026-11-04\n\n- Actual recorded release.\n")
        self.assertEqual(self.run_tool("check").returncode, 0)
        result = self.run_tool("bump", "0.4.0-dev.2", "--note", "Next work.", "--write")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## [0.4.0-dev.1] - 2026-11-04", (self.root / "CHANGELOG.md").read_text())
        self.assertEqual(self.run_tool("check").returncode, 0)

    def test_check_rejects_invalid_release_date(self):
        (self.root / "CHANGELOG.md").write_text("## [0.4.0-dev.1] - 2026-02-30\n\n- A note.\n")
        self.assertNotEqual(self.run_tool("check").returncode, 0)


class PackagingTests(unittest.TestCase):
    def test_manifest_entry_points_and_runtime_payload_are_present(self):
        root = TOOL.parents[1]
        manifest = json.loads((root / "manifest.json").read_text())
        self.assertEqual(manifest['schemaVersion'], 1)
        self.assertEqual(manifest['id'], 'silexmachina.omastrix')
        self.assertEqual(manifest['kinds'], ['bar-widget'])
        self.assertEqual(manifest['entryPoints'], {'barWidget': 'Panel.qml'})
        self.assertIn(manifest['barWidget']['defaultSection'], ('left', 'center', 'right'))
        payload = ('ActionButton.qml', 'View.js', 'bin/omastrix', 'bin/library.py',
                   'bin/webui.py', 'bin/omastrix-engine-install', 'catalog.json',
                   'engine-pin.json', 'LICENSE', *manifest['entryPoints'].values())
        for relative in payload:
            with self.subTest(path=relative):
                path = root / relative
                self.assertTrue(path.is_file(), 'Missing runtime/package file')
                self.assertFalse(path.is_symlink(), 'Omarchy refuses plugin symlinks')
        for relative in ('bin/omastrix', 'bin/omastrix-engine-install'):
            self.assertTrue(os.access(root / relative, os.X_OK), relative)

    def test_ci_compiles_the_extensionless_backend_entrypoint(self):
        workflow = (TOOL.parents[1] / ".github/workflows/check.yml").read_text()
        self.assertIn('python3 -m py_compile bin/omastrix', workflow)

    def test_ci_checks_committed_whitespace(self):
        workflow = (TOOL.parents[1] / ".github/workflows/check.yml").read_text()
        whitespace_step = workflow.split("- name: Whitespace", 1)[1]
        self.assertIn("git show --format= --check HEAD", whitespace_step)


if __name__ == "__main__":
    unittest.main()
