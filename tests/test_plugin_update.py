"""Offline updater tests; never use the installed checkout or native updater."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class PluginUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        spec = importlib.util.spec_from_file_location("plugin_update", ROOT / "bin/plugin_update.py")
        assert spec is not None and spec.loader is not None
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.repo = self.home / "checkout"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        self.manifest("1.0.0")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")
        installed = self.home / ".config/omarchy/plugins/silexmachina.omastrix"
        installed.parent.mkdir(parents=True)
        installed.symlink_to(self.repo, target_is_directory=True)
        self.root_patch = patch.object(self.mod, "root_dir", return_value=self.repo)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.STDOUT, text=True).strip()

    def manifest(self, version, identity="silexmachina.omastrix"):
        (self.repo / "manifest.json").write_text(json.dumps({"id": identity, "version": version}))

    def test_snapshot_contract_is_local_and_accepts_development_symlink(self):
        state = self.mod.status()
        self.assertEqual(set(state), {"managed", "version", "current_commit", "latest_version", "latest_commit", "update_available", "updating", "error", "checked_at"})
        self.assertTrue(state["managed"])
        self.assertEqual(state["version"], "1.0.0")
        self.assertEqual(state["current_commit"], self.git("rev-parse", "HEAD"))
        self.assertFalse(state["update_available"])
        self.assertEqual(state["checked_at"], "")
        self.assertFalse((self.home / ".local/state/omastrix").exists())
    def remote(self, version="1.1.0", identity="silexmachina.omastrix"):
        old = self.git("rev-parse", "HEAD")
        self.manifest(version, identity)
        self.git("add", ".")
        self.git("commit", "-qm", "remote update")
        latest = self.git("rev-parse", "HEAD")
        remote = self.home / "remote.git"
        subprocess.run(["git", "clone", "--bare", str(self.repo), str(remote)], check=True, capture_output=True)
        self.git("reset", "--hard", old)
        self.git("remote", "add", "origin", str(remote))
        return latest

    def test_check_persists_validated_remote_and_snapshot_never_fetches(self):
        latest = self.remote()
        self.assertTrue(self.mod.check()["success"])
        state = self.mod.status()
        self.assertEqual(state["latest_commit"], latest)
        self.assertEqual(state["latest_version"], "1.1.0")
        self.assertTrue(state["checked_at"])
        self.assertTrue(state["update_available"])
        self.git("remote", "remove", "origin")
        self.assertTrue(self.mod.status()["update_available"])
        self.assertFalse(self.mod.check()["success"])
        self.assertTrue(self.mod.status()["error"])
        self.assertFalse(self.mod.status()["update_available"])

    def test_dirty_and_diverged_checkout_are_blocked(self):
        self.remote()
        (self.repo / "untracked").write_text("local")
        self.assertFalse(self.mod.check()["success"])
        (self.repo / "untracked").unlink()
        (self.repo / "local").write_text("local")
        self.git("add", ".")
        self.git("commit", "-qm", "diverged")
        self.assertFalse(self.mod.check()["success"])
        self.assertIn("diverged", self.mod.status()["error"])

    def test_local_ahead_is_not_an_update_and_wrong_manifest_is_rejected(self):
        self.remote()
        self.git("fetch", "origin", "HEAD")
        self.git("merge", "--ff-only", "FETCH_HEAD")
        (self.repo / "local").write_text("local")
        self.git("add", ".")
        self.git("commit", "-qm", "ahead")
        self.assertTrue(self.mod.check()["success"])
        self.assertFalse(self.mod.status()["update_available"])

    def test_invalid_remote_manifest_and_unmanaged_checkout_are_blocked(self):
        self.remote(identity="someone.else")
        self.assertFalse(self.mod.check()["success"])
        self.assertIn("manifest", self.mod.status()["error"])
        (self.home / ".config/omarchy/plugins/silexmachina.omastrix").unlink()
        self.assertFalse(self.mod.check()["success"])
        self.assertFalse(self.mod.status()["managed"])
    def native(self, mode="update"):
        bindir = self.home / "fakebin"
        bindir.mkdir(exist_ok=True)
        script = bindir / "omarchy"
        script.write_text('#!/bin/sh\n' +
            'printf "%s\\n" "$*" > "$HOME/native-args"\n' +
            ('echo native-failure >&2; exit 7\n' if mode == "fail" else
             'exit 0\n' if mode == "noop" else
             'git -C "$HOME/checkout" fetch --quiet origin HEAD && git -C "$HOME/checkout" merge --ff-only FETCH_HEAD\n'))
        script.chmod(0o755)
        os.environ["PATH"] = str(bindir) + os.pathsep + os.environ["PATH"]

    def test_worker_reads_back_native_update_and_preserves_services(self):
        latest = self.remote()
        self.native()
        self.assertTrue(self.mod.update_run()["success"])
        state = self.mod.status()
        self.assertEqual(state["version"], "1.1.0")
        self.assertEqual(state["current_commit"], latest)
        self.assertFalse(state["updating"])
        self.assertFalse(state["update_available"])
        self.assertEqual(self.mod.read_state()["pid"], 0)
        self.assertEqual((self.home / "native-args").read_text().strip(), "plugin update silexmachina.omastrix --yes")

    def test_worker_nonzero_and_noop_never_report_success(self):
        self.remote()
        self.native("fail")
        self.assertFalse(self.mod.update_run()["success"])
        self.assertIn("native-failure", self.mod.status()["error"])
        self.assertEqual(self.mod.read_state()["pid"], 0)
        self.native("noop")
        self.assertFalse(self.mod.update_run()["success"])
        self.assertTrue(self.mod.status()["error"])

    def test_worker_rechecks_dirty_and_lock_contention_does_not_clobber_state(self):
        self.remote()
        self.native()
        self.assertTrue(self.mod.check()["success"])
        (self.repo / "dirty").write_text("dirty")
        self.assertFalse(self.mod.update_run()["success"])
        self.assertFalse((self.home / "native-args").exists())
        before = self.mod.read_state()
        fd = self.mod.acquire_lock()
        try:
            self.assertFalse(self.mod.start_update()["success"])
            self.assertFalse(self.mod.check()["success"])
            self.assertFalse(self.mod.update_run()["success"])
            self.assertEqual(self.mod.read_state(), before)
        finally:
            os.close(fd)

    def test_state_symlink_is_rejected_without_touching_target(self):
        self.remote()
        directory = self.home / ".local/state/omastrix"
        directory.mkdir(parents=True)
        target = self.home / "untouched"
        target.write_text("original")
        (directory / "plugin-update.json").symlink_to(target)
        self.assertFalse(self.mod.check()["success"])
        self.assertEqual(target.read_text(), "original")
        self.assertTrue(self.mod.status()["error"])

    def test_launcher_detaches_and_worker_finishes_with_inherited_lock(self):
        import time
        wrapper = self.repo / "bin/omastrix"
        wrapper.parent.mkdir()
        wrapper.write_text('#!/usr/bin/env python3\nimport sys\nsys.path.insert(0, ' + repr(str(ROOT / "bin")) + ')\nimport plugin_update as p\nfrom pathlib import Path\np.root_dir = lambda: Path(' + repr(str(self.repo)) + ')\nr = p.update_run()\nraise SystemExit(0 if r["success"] else 1)\n')
        wrapper.chmod(0o755)
        self.git("add", ".")
        self.git("commit", "-qm", "test runner")
        latest = self.remote()
        self.native()
        self.assertTrue(self.mod.check()["success"])
        self.assertTrue(self.mod.start_update()["success"])
        deadline = time.monotonic() + 5
        while self.mod.busy() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.mod._workers[0].wait(timeout=5)
        self.assertFalse(self.mod.busy())
        self.assertEqual(self.mod.status()["current_commit"], latest)
        self.assertEqual(self.mod.read_state()["pid"], 0)
        self.assertEqual(self.mod.status()["error"], "")
    def test_abandoned_job_is_error_not_silent_success(self):
        self.remote()
        self.assertTrue(self.mod.check()["success"])
        saved = self.mod.read_state()
        saved["pid"] = 999999999
        self.mod.save_state(saved)
        state = self.mod.status()
        self.assertFalse(state["updating"])
        self.assertFalse(state["update_available"])
        self.assertIn("without recording completion", state["error"])

    def test_launcher_spawn_failure_clears_pid_and_persists_error(self):
        self.remote()
        self.assertTrue(self.mod.check()["success"])
        self.assertFalse(self.mod.start_update()["success"])
        self.assertEqual(self.mod.read_state()["pid"], 0)
        self.assertTrue(self.mod.status()["error"])

    def test_state_directory_and_lock_symlinks_are_blocked(self):
        directory = self.home / ".local/state/omastrix"
        directory.parent.mkdir(parents=True)
        outside = self.home / "outside"
        outside.mkdir()
        directory.symlink_to(outside, target_is_directory=True)
        self.assertFalse(self.mod.check()["success"])
        self.assertEqual(list(outside.iterdir()), [])
        directory.unlink()
        directory.mkdir()
        target = outside / "lock"
        target.write_text("keep")
        (directory / "plugin.lock").symlink_to(target)
        self.assertFalse(self.mod.update_run()["success"])
        self.assertEqual(target.read_text(), "keep")

    def test_check_lock_is_not_reported_as_background_update(self):
        self.remote()
        fd = self.mod.acquire_lock()
        try:
            self.assertFalse(self.mod.status()["updating"])
        finally:
            os.close(fd)

    def test_cached_state_cannot_hide_invalid_current_manifest(self):
        self.remote()
        self.assertTrue(self.mod.check()["success"])
        self.manifest("1.0.0", "someone.else")
        state = self.mod.status()
        self.assertFalse(state["managed"])
        self.assertIn("manifest", state["error"])

    def test_native_update_has_timeout_and_persists_timeout_failure(self):
        self.remote()
        original = subprocess.run
        def run(args, **kwargs):
            if args[:3] == ["omarchy", "plugin", "update"]:
                self.assertGreater(kwargs.get("timeout", 0), 0)
                raise subprocess.TimeoutExpired(args, kwargs["timeout"])
            return original(args, **kwargs)
        with patch.object(self.mod.subprocess, "run", side_effect=run):
            self.assertFalse(self.mod.update_run()["success"])
        self.assertEqual(self.mod.read_state()["pid"], 0)
        self.assertIn("timed out", self.mod.status()["error"])

    def test_cli_dispatch_and_snapshot_plugin_integration(self):
        import runpy
        import sys
        # Load main without calling hardware/network probes, then stub its host snapshot dependencies.
        with patch.dict(sys.modules, {"plugin_update": self.mod}):
            app = runpy.run_path(str(ROOT / "bin/omastrix"))
            for verb, name in (("plugin-check", "check"), ("plugin-update", "start_update"),
                               ("plugin-update-run", "update_run")):
                with patch.object(self.mod, name, return_value={"success": True}) as action:
                    with patch.object(sys, "argv", ["omastrix", verb]):
                        self.assertEqual(app["main"](), 0)
                    action.assert_called_once_with()
            snapshot_globals = app["snapshot"].__globals__
            from contextlib import ExitStack
            with ExitStack() as stack:
                for key, value in {"host_probe": ("", {}, "", "", "", False),
                                   "mem_total_bytes": None, "pages_limit": None,
                                   "configured_pages": None, "engine_info": {},
                                   "webui_info": {}}.items():
                    stack.enter_context(patch.dict(snapshot_globals, {key: lambda value=value: value}))
                stack.enter_context(patch.object(snapshot_globals["library"], "library_view", return_value={}))
                stack.enter_context(patch.object(snapshot_globals["library"], "write_preset"))
                self.assertEqual(app["snapshot"]()["plugin"], self.mod.status())


if __name__ == "__main__":
    unittest.main()
