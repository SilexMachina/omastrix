"""Package approval: isolated fake tools only, no privilege or network calls."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

BIN = Path(__file__).resolve().parents[1] / 'bin'
sys.path.insert(0, str(BIN))


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.tools = self.home / 'tools'
        self.tools.mkdir()
        self.db = self.home / 'packages.json'
        self.db.write_text('[]')
        self.log = self.home / 'commands'
        script = f'''#!{sys.executable}
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
db = Path(os.environ['PACKAGE_DB'])
with open(os.environ['PACKAGE_LOG'], 'a') as f: f.write(json.dumps([name] + args) + '\\n')
if name == 'pacman' and args[:2] == ['-Q', '--']:
    sys.exit(0 if args[2] in json.loads(db.read_text()) else 1)
if name == 'pkexec' and args[:3] == ['/usr/bin/omarchy', 'pkg', 'add']:
    if os.environ.get('DENY'): sys.exit(126)
    os.execv(str(Path(sys.argv[0]).parent / 'omarchy'), ['omarchy'] + args[1:])
if name == 'omarchy' and args[:2] == ['pkg', 'add']:
    if not os.environ.get('NO_REGISTER'): db.write_text(json.dumps(args[2:]))
    sys.exit(0)
sys.exit('unexpected command: ' + repr(sys.argv))
'''
        for name in ('pacman', 'pkexec', 'omarchy'):
            path = self.tools / name
            path.write_text(script)
            path.chmod(0o755)
        patcher = mock.patch.dict(os.environ, {'HOME': str(self.home), 'PATH': str(self.tools),
                                              'PACKAGE_DB': str(self.db), 'PACKAGE_LOG': str(self.log)}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        import dependencies
        self.deps = dependencies

    def commands(self):
        return [json.loads(s) for s in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_missing_packages_check_only_and_fixed_host_allowlist(self):
        missing = self.deps.missing('engine', strix=False)
        self.assertEqual(missing, ['base-devel', 'git', 'cmake', 'ninja', 'vulkan-headers',
                                   'vulkan-tools', 'spirv-headers', 'shaderc'])
        self.assertEqual(self.deps.missing('engine', strix=True), missing + ['vulkan-radeon'])
        self.assertTrue(all(c[:3] == ['pacman', '-Q', '--'] for c in self.commands()))
        self.assertEqual(json.loads(self.db.read_text()), [])
        approval = self.deps.approval(['uv'])
        self.assertEqual(approval['confirmation'], 'dependencies')
        self.assertTrue(approval['needs_confirm'])
        self.assertFalse(approval['success'])
        self.assertEqual(approval['packages'], ['uv'])
        self.assertIn('uv', approval['error'])

    def test_install_rechecks_then_runs_root_owned_omarchy_and_verifies(self):
        self.deps.install('webui')
        self.assertEqual(self.commands(), [['pacman', '-Q', '--', 'uv'],
            ['pkexec', '/usr/bin/omarchy', 'pkg', 'add', 'uv'], ['omarchy', 'pkg', 'add', 'uv'],
            ['pacman', '-Q', '--', 'uv']])
        self.log.unlink()
        self.deps.install('webui')
        self.assertEqual(self.commands(), [['pacman', '-Q', '--', 'uv']])

    def test_denial_and_unregistered_success_are_errors(self):
        for variable in ('DENY', 'NO_REGISTER'):
            with self.subTest(variable=variable), mock.patch.dict(os.environ, {variable: '1'}):
                with self.assertRaisesRegex(ValueError, 'dependencies'):
                    self.deps.install('webui')

    def test_engine_worker_uses_fake_dependencies_then_exact_unprivileged_installer(self):
        installer = self.tools / 'engine-installer'
        installer.write_text('#!' + sys.executable + '\nimport json,sys\nwith open(' + repr(str(self.log)) + ', "a") as f: f.write(json.dumps(["build"] + sys.argv[1:]) + "\\n")\n')
        installer.chmod(0o755)
        code = '''import runpy, sys
ns = runpy.run_path(sys.argv[1])
run = ns['engine_update_run']
g = run.__globals__
original = g['engine_paths']
def paths():
    p = original()
    p['installer'] = sys.argv[2]
    return p
g['engine_paths'] = paths
g['host_probe'] = lambda: (False,)
g['systemctl'] = lambda *args: (3, 'inactive')
raise SystemExit(run('a' * 40, first_install=True, install_dependencies=True))
'''
        for denied in (True, False):
            with self.subTest(denied=denied):
                self.db.write_text('[]')
                self.log.unlink(missing_ok=True)
                env = dict(os.environ)
                if denied:
                    env['DENY'] = '1'
                out = subprocess.run([sys.executable, '-c', code, str(BIN / 'omastrix'), str(installer)],
                                     env=env, capture_output=True, text=True, timeout=15)
                self.assertEqual(out.returncode, 1 if denied else 0, out.stdout + out.stderr)
                state = json.loads((self.home / '.local/state/omastrix/engine-update.json').read_text())
                self.assertEqual(state['pid'], 0)
                builds = [c for c in self.commands() if c[0] == 'build']
                self.assertEqual(builds, [] if denied else [['build', '--first-install', 'a' * 40]])
                if denied:
                    self.assertIn('dependencies', state['error'])

    def test_unknown_dependency_target_cannot_become_package_arguments(self):
        with self.assertRaises(ValueError):
            self.deps.install('--overwrite')
        self.assertEqual(self.commands(), [])


if __name__ == '__main__':
    unittest.main()
