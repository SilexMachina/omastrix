"""WebUI process tests: isolated HOME and fake tools, no packages or services."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WebuiInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.repo = self.home / "plugin"
        (self.repo / "bin").mkdir(parents=True)
        for name in ("webui.py", "library.py"):
            shutil.copy2(ROOT / "bin" / name, self.repo / "bin" / name)
        if (ROOT / "webui-pin.json").exists():
            shutil.copy2(ROOT / "webui-pin.json", self.repo / "webui-pin.json")
        self.tools = self.home / "tools"
        self.tools.mkdir()
        self.log = self.home / "commands.jsonl"
        self.control = self.home / "control.json"
        self.settings = {}
        stub = f'''#!{sys.executable}
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
c = json.loads(Path(os.environ["CONTROL"]).read_text())
with open(os.environ["COMMAND_LOG"], "a") as out: out.write(json.dumps([Path(sys.argv[0]).name] + args) + "\\n")
if Path(sys.argv[0]).name == "systemctl":
    if "is-active" in args:
        print(c.get("state", "inactive")); sys.exit(c.get("state_code", 3))
    if "show" in args:
        print(c.get("show_state", "")); sys.exit(c.get("show_code", 0))
    sys.exit(c.get("reload_code", 0))
if args[0] == "venv":
    p = Path(args[1]); (p / "bin").mkdir(parents=True)
    (p / "pyvenv.cfg").write_text("version = 3.11.0\\n")
    body = {('#!' + sys.executable + chr(10))!r} + 'import json,os,sys\\nfrom pathlib import Path\\nc=json.loads(Path(os.environ["CONTROL"]).read_text())\\nprint(c.get("python_version", "3.11") if "sys.version_info" in sys.argv[-1] else c.get("actual_version", Path(__file__).parent.parent.joinpath("version").read_text()))\\nsys.exit(c.get("version_code",0))\\n'
    (p / "bin/python").write_text(body); (p / "bin/python").chmod(0o755)
    (p / "bin/open-webui").write_text("#!/bin/sh\\nexit 0\\n"); (p / "bin/open-webui").chmod(0o755)
    sys.exit(c.get("venv_code", 0))
if args[:2] == ["pip", "install"]:
    p = Path(args[args.index("--python")+1]).parent.parent
    version = args[-1].split("==")[-1]
    (p / "version").write_text(version)
    if c.get("missing_cli"): (p / "bin/open-webui").unlink()
    if c.get("start_during_build"):
        c["state"] = "active"; c["state_code"] = 0
        Path(os.environ["CONTROL"]).write_text(json.dumps(c))
    if c.get("redirect_config"):
        config = Path(os.environ["HOME"]) / ".config"
        config.symlink_to(Path(os.environ["HOME"]) / "unrelated", target_is_directory=True)
    sys.exit(c.get("install_code", 0))
if args[:2] == ["pip", "check"]: sys.exit(c.get("check_code", 0))
sys.exit(99)
'''
        for name in ("uv", "systemctl"):
            path = self.tools / name
            path.write_text(stub)
            path.chmod(0o755)
        self.prefix = self.home / ".local/share/omastrix/webui"
        self.envfile = self.home / ".config/omastrix/webui.env"

    def run_worker(self, version=None, action=None):
        self.control.write_text(json.dumps(self.settings))
        expr = action or ("webui.install()" if version is None else "webui.update_run(%r)" % version)
        return subprocess.run(
            [sys.executable, "-c", "import webui; raise SystemExit(" + expr + ")"],
            env={"HOME": str(self.home), "PATH": str(self.tools),
                 "PYTHONPATH": str(self.repo / "bin"), "CONTROL": str(self.control),
                 "COMMAND_LOG": str(self.log)}, capture_output=True, text=True, timeout=15,
        )

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def state(self, update=False):
        return json.loads((self.home / (".local/state/omastrix/webui-update.json" if update else ".local/state/omastrix/webui-install.json")).read_text())

    def make_legacy(self):
        self.assertEqual(self.run_worker().returncode, 0)
        current = (self.prefix / "venv").resolve()
        (self.prefix / "venv").unlink()
        (current / ".omastrix.json").unlink()
        current.rename(self.prefix / "venv")
        return self.prefix / "venv"

    def test_legacy_directory_migrates_only_on_success_and_can_rollback(self):
        legacy = self.make_legacy()
        self.settings = {"reload_code": 1}
        out = self.run_worker("0.14.0")
        self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertFalse(legacy.is_symlink())
        self.assertEqual((legacy / "version").read_text(), "0.13.0")
        self.settings = {}
        out = self.run_worker("0.14.0")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(legacy.is_symlink())
        self.assertEqual((legacy / "version").read_text(), "0.14.0")
        self.assertTrue(any((p / "version").read_text() == "0.13.0" for p in (self.prefix / "venvs").iterdir()))

    def test_missing_unit_first_install_completes_without_starting_service(self):
        self.settings = {"state": "inactive", "state_code": 4,
                         "show_state": "LoadState=not-found\nActiveState=inactive"}
        out = self.run_worker()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue((self.prefix / "venv/bin/open-webui").is_file())
        self.assertEqual(self.state()["pid"], 0)
        self.assertEqual(self.state()["error"], "")
        self.assertFalse(any(command[0] == "systemctl" and "start" in command for command in self.commands()))

    def test_install_refuses_running_or_unknown_service_before_build(self):
        for state, code in (("active", 0), ("unknown", 4), ("inactive", 1), ("activating", 0)):
            with self.subTest(state=state, code=code):
                self.settings = {"state": state, "state_code": code}
                self.log.unlink(missing_ok=True)
                out = self.run_worker()
                self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)
                self.assertFalse(any(c[0] == "uv" for c in self.commands()))
                self.assertTrue(self.state()["error"])

    def test_invalid_update_version_records_failure(self):
        out = self.run_worker("--help")
        self.assertNotEqual(out.returncode, 0)
        self.assertTrue(self.state(True)["error"])
        self.assertEqual(self.state(True)["pid"], 0)

    def test_unverified_initial_build_never_publishes_or_claims_success(self):
        for failure in ({"venv_code": 1}, {"install_code": 1}, {"check_code": 1},
                        {"actual_version": "0.12.0"}, {"version_code": 1}, {"python_version": "3.12"},
                        {"missing_cli": True}):
            with self.subTest(failure=failure):
                self.settings = failure
                out = self.run_worker()
                self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)
                self.assertFalse((self.prefix / "venv").exists())
                self.assertFalse(self.envfile.exists())
                self.assertTrue(self.state()["error"])
                self.assertEqual(self.state()["pid"], 0)

    def test_final_state_write_failure_rolls_back_even_after_pointer_switch(self):
        legacy = self.make_legacy()
        # Inject a failure only on the success job-state write, not failure reporting.
        # exec statements cannot be nested in SystemExit; use an expression tuple.
        action = "(exec(" + repr("original = webui.library.atomic_json\ndef fail(path, data):\n    if path == webui.update_state_path() and data.get('error') == '':\n        raise OSError('state disk full')\n    return original(path, data)\nwebui.library.atomic_json = fail") + "), webui.update_run('0.14.0'))[1]"
        out = self.run_worker(action=action)
        self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertFalse(legacy.is_symlink())
        self.assertEqual((legacy / "version").read_text(), "0.13.0")
        self.assertFalse((legacy / ".omastrix.json").exists())
        self.assertIn("state disk full", self.state(True)["error"])

    def test_ancestor_symlinks_refused_before_lock_or_tools(self):
        for relative in (".local", ".local/state", ".local/share", ".config", ".config/systemd", ".local/share/omastrix/bin"):
            with self.subTest(relative=relative):
                link = self.home / relative
                target = self.home / "unrelated"
                target.mkdir(exist_ok=True)
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(target, target_is_directory=True)
                self.log.unlink(missing_ok=True)
                try:
                    out = self.run_worker()
                    self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)
                    self.assertEqual(list(target.iterdir()), [])
                    self.assertEqual(self.commands(), [])
                finally:
                    link.unlink()
                    for directory in (self.home / ".local", self.home / ".config", target):
                        if directory.exists(): shutil.rmtree(directory)

    def test_foreign_pointer_is_not_executed_or_replaced(self):
        target = self.home / ".local/share/open-webui/venv"
        (target / "bin").mkdir(parents=True)
        executable = target / "bin/open-webui"
        executable.write_text("#!/bin/sh\nexit 0\n")
        executable.chmod(0o755)
        self.prefix.mkdir(parents=True)
        (self.prefix / "venv").symlink_to(target, target_is_directory=True)
        out = self.run_worker()
        self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(os.readlink(self.prefix / "venv"), str(target))
        self.assertEqual(self.commands(), [])
        self.assertTrue(self.state()["error"])

    def test_managed_metadata_must_be_valid_and_match_distribution(self):
        self.assertEqual(self.run_worker().returncode, 0)
        metadata = (self.prefix / "venv").resolve() / ".omastrix.json"
        for body in ("[]", "{}", "not json", '{"schema":1,"version":"0.12.0","python":"3.11"}'):
            with self.subTest(body=body):
                metadata.write_text(body)
                self.log.unlink()
                out = self.run_worker("0.14.0")
                self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)
                self.assertFalse(any(c[0] == "uv" for c in self.commands()))
                self.assertTrue(self.state(True)["error"])

    def test_failed_promotion_restores_pointer_and_layout(self):
        self.assertEqual(self.run_worker().returncode, 0)
        old = os.readlink(self.prefix / "venv")
        wrapper = self.home / ".local/share/omastrix/bin/omastrix-webui"
        unit = self.home / ".config/systemd/user/omastrix-webui.service"
        wrapper.write_text("# previous wrapper\n")
        unit.write_text("# previous unit\n")
        for failure in ({"reload_code": 1}, {"start_during_build": True}):
            with self.subTest(failure=failure):
                self.settings = failure
                out = self.run_worker("0.14.0")
                self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)
                self.assertEqual(os.readlink(self.prefix / "venv"), old)
                self.assertEqual(wrapper.read_text(), "# previous wrapper\n")
                self.assertEqual(unit.read_text(), "# previous unit\n")
                self.assertTrue(self.state(True)["error"])
                self.assertEqual(self.state(True)["pid"], 0)

    def test_update_builds_new_venv_without_mutating_old_or_user_data(self):
        self.assertEqual(self.run_worker().returncode, 0)
        old = (self.prefix / "venv").resolve()
        self.envfile.write_text("# existing settings and secret sentinel\n")
        data = self.prefix / "data/webui.db"
        data.parent.mkdir()
        data.write_bytes(b"database sentinel")
        hand = self.home / ".local/share/open-webui/sentinel"
        hand.parent.mkdir()
        hand.write_bytes(b"unrelated")
        self.log.unlink()
        out = self.run_worker("0.14.0")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotEqual((self.prefix / "venv").resolve(), old)
        self.assertEqual((old / "version").read_text(), "0.13.0")
        self.assertEqual(data.read_bytes(), b"database sentinel")
        self.assertEqual(hand.read_bytes(), b"unrelated")
        self.assertEqual(self.envfile.read_text(), "# existing settings and secret sentinel\n")
        self.assertTrue(any(c[1:3] == ["pip", "check"] for c in self.commands()))
        self.assertEqual(self.state(True)["version"], "0.14.0")

    def test_install_launcher_refuses_foreign_pointer(self):
        target = self.home / "foreign"
        (target / "bin").mkdir(parents=True)
        binary = target / "bin/open-webui"
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o755)
        self.prefix.mkdir(parents=True)
        (self.prefix / "venv").symlink_to(target, target_is_directory=True)
        out = self.run_worker(action="0 if webui.start_install()['success'] else 1")
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(self.commands(), [])

    def test_bad_metadata_value_types_are_reported_as_job_failures(self):
        self.assertEqual(self.run_worker().returncode, 0)
        metadata = (self.prefix / "venv").resolve() / ".omastrix.json"
        metadata.write_text('{"schema":1,"version":13,"python":"3.11"}')
        out = self.run_worker("0.14.0")
        self.assertNotEqual(out.returncode, 0)
        self.assertTrue(self.state(True)["error"])
        self.assertEqual(self.state(True)["pid"], 0)

    def test_status_refuses_foreign_pointer_without_executing_it(self):
        target = self.home / "foreign"
        (target / "bin").mkdir(parents=True)
        for name in ("open-webui", "python"):
            binary = target / "bin" / name
            binary.write_text("#!" + sys.executable + "\nfrom pathlib import Path\nPath(" + repr(str(self.home / "executed-foreign")) + ").touch()\n")
            binary.chmod(0o755)
        self.prefix.mkdir(parents=True)
        (self.prefix / "venv").symlink_to(target, target_is_directory=True)
        out = self.run_worker(action="0 if webui.status()['state'] == 'unavailable' else 1")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertFalse((self.home / "executed-foreign").exists())

    def test_missing_uv_worker_records_failure(self):
        (self.tools / "uv").unlink()
        out = self.run_worker()
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(self.state()["pid"], 0)
        self.assertIn("requires uv", self.state()["error"])

    def test_ancestor_redirection_during_build_is_rechecked_before_promotion(self):
        target = self.home / "unrelated"
        target.mkdir()
        self.settings = {"redirect_config": True}
        out = self.run_worker()
        self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(list(target.iterdir()), [])
        self.assertFalse((self.prefix / "venv").exists())
        self.assertTrue(self.state()["error"])

    def test_repeated_install_preserves_newer_version_and_clears_stale_job_error(self):
        self.assertEqual(self.run_worker().returncode, 0)
        self.assertEqual(self.run_worker("0.14.0").returncode, 0)
        pointer = os.readlink(self.prefix / "venv")
        state = self.home / ".local/state/omastrix/webui-install.json"
        state.write_text('{"pid":0,"error":"old failure"}')
        self.log.unlink()
        out = self.run_worker()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(os.readlink(self.prefix / "venv"), pointer)
        self.assertEqual((self.prefix / "venv/version").read_text(), "0.14.0")
        self.assertEqual(self.state()["error"], "")
        self.assertFalse(any(c[0] == "uv" for c in self.commands()))

    def test_repeated_install_safely_migrates_legacy_without_self_pointer(self):
        self.make_legacy()
        (self.prefix / "venvs").rmdir()
        out = self.run_worker()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue((self.prefix / "venv").is_symlink())
        self.assertEqual((self.prefix / "venv/version").read_text(), "0.13.0")
        out = self.run_worker()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_legacy_install_dependency_failure_never_promotes(self):
        legacy = self.make_legacy()
        self.settings = {"check_code": 1}
        out = self.run_worker()
        self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertFalse(legacy.is_symlink())
        self.assertTrue(self.state()["error"])

    def test_legacy_migration_rebuilds_same_version_instead_of_reusing_relocated_venv(self):
        legacy = self.make_legacy()
        (legacy / "version").write_text("0.14.0")
        self.log.unlink()
        out = self.run_worker()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual((legacy / "version").read_text(), "0.14.0")
        self.assertTrue(any(c[-1] == "open-webui==0.14.0" for c in self.commands()))

    def test_existing_install_launcher_refuses_running_service_without_rewriting_layout(self):
        self.assertEqual(self.run_worker().returncode, 0)
        wrapper = self.home / ".local/share/omastrix/bin/omastrix-webui"
        wrapper.write_text("# running wrapper sentinel\n")
        self.settings = {"state": "active", "state_code": 0}
        self.log.unlink()
        out = self.run_worker(action="0 if webui.start_install()['success'] else 1")
        self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(wrapper.read_text(), "# running wrapper sentinel\n")
        self.assertFalse(any("daemon-reload" in c for c in self.commands()))

    def test_initial_install_pins_and_verifies_an_immutable_venv(self):
        out = self.run_worker()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        installs = [c for c in self.commands() if c[1:3] == ["pip", "install"]]
        self.assertEqual(installs[0][-1], "open-webui==0.13.0")
        pointer = self.prefix / "venv"
        self.assertTrue(pointer.is_symlink())
        self.assertNotEqual(Path(installs[0][installs[0].index("--python") + 1]).parent.parent, pointer)
        self.assertTrue(any(c[1:3] == ["pip", "check"] for c in self.commands()))
        self.assertEqual(self.state()["error"], "")
        self.assertFalse(any(c[1] in ("start", "stop", "restart", "enable") for c in self.commands() if c[0] == "systemctl"))


if __name__ == "__main__":
    unittest.main()
