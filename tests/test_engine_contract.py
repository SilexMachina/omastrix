"""CLI contracts for missing user units and failed update checks."""
import contextlib
import io
import json
import subprocess
from pathlib import Path
from unittest import mock

from test_backend_safety import IsolatedBackend, backend


class EngineContractTests(IsolatedBackend):
    def setUp(self):
        super().setUp()
        probe = mock.patch.object(backend, "gpu_devices", return_value=[])
        probe.start()
        self.addCleanup(probe.stop)
        deps = mock.patch.object(backend.dependencies, "missing", return_value=[])
        deps.start()
        self.addCleanup(deps.stop)
        self.real_lookup = backend.newest_halo_tag
        lookup = mock.patch.object(backend, "newest_halo_tag", return_value=(12345, "b12345", "a" * 40))
        lookup.start()
        self.addCleanup(lookup.stop)

    def test_dependency_approval_does_not_lookup_build_or_launch_packages(self):
        with mock.patch.object(backend, "engine_info", return_value={"state": "not_installed"}), \
             mock.patch.object(backend.dependencies, "missing", return_value=["cmake", "ninja"]), \
             mock.patch.object(backend, "newest_halo_tag") as lookup, \
             mock.patch("subprocess.Popen") as spawn:
            result = backend.start_engine_install()
        self.assertEqual(result["confirmation"], "dependencies")
        self.assertEqual(result["packages"], ["cmake", "ninja"])
        lookup.assert_not_called()
        spawn.assert_not_called()
        self.assertFalse(Path(backend.engine_paths()["update"]).exists())

    def test_confirmed_dependencies_launch_detached_exact_selection_and_remain_pollable(self):
        with mock.patch.object(backend, "engine_info", return_value={"state": "not_installed"}), \
             mock.patch.object(backend.dependencies, "missing", return_value=["git"]), \
             mock.patch("subprocess.Popen", return_value=mock.Mock(pid=12345)) as spawn:
            self.assertTrue(backend.start_engine_install(confirm=True)["success"])
        self.assertEqual(spawn.call_args.args[0][1:], ["engine-dependencies-run", "a" * 40])
        self.assertTrue(spawn.call_args.kwargs["start_new_session"])
        saved = backend.read_json(backend.engine_paths()["update"])
        self.assertEqual(saved["phase"], "dependencies")
        self.assertEqual(saved["pid"], 12345)
        with mock.patch.object(backend, "systemctl", return_value=(4, "inactive")), \
             mock.patch.object(backend, "port_open", return_value=False), \
             mock.patch.object(backend, "pid_alive", return_value=True):
            info = backend.engine_info()
        self.assertEqual(info["state"], "installing")
        self.assertFalse(info["installed"])

    def test_dependency_denial_persists_pid_zero_without_engine_build(self):
        with mock.patch.object(backend, "systemctl", return_value=(3, "inactive")), \
             mock.patch.object(backend.dependencies, "install", side_effect=ValueError("dependencies denied")), \
             mock.patch("subprocess.call") as build, self.quiet():
            self.assertEqual(backend.engine_update_run("a" * 40, first_install=True, install_dependencies=True), 1)
        build.assert_not_called()
        saved = backend.read_json(backend.engine_paths()["update"])
        self.assertEqual(saved["pid"], 0)
        self.assertIn("dependencies denied", saved["error"])

    def test_confirmed_webui_launcher_never_installs_packages_in_foreground(self):
        webui = backend.webui
        with mock.patch.object(webui, "current_venv", return_value=None), \
             mock.patch.object(webui, "require_stopped"), \
             mock.patch.object(webui, "find_uv", return_value=""), \
             mock.patch.object(webui.dependencies, "install") as packages, \
             mock.patch("subprocess.Popen", return_value=mock.Mock(pid=12345)) as spawn:
            self.assertTrue(webui.start_install(confirm=True)["success"])
        packages.assert_not_called()
        self.assertEqual(spawn.call_args.args[0][1:], ["webui-install-run", "--confirm"])
        self.assertTrue(spawn.call_args.kwargs["start_new_session"])
        saved = webui.read_json(webui.install_state_path())
        self.assertEqual(saved["phase"], "dependencies")
        self.assertEqual(saved["pid"], 12345)

    def test_confirm_dispatch_for_both_installers(self):
        for verb, target in (("engine-install", "start_engine_install"), ("webui-install", "start_install")):
            module = backend if verb == "engine-install" else backend.webui
            with mock.patch("sys.argv", ["omastrix", verb, "--confirm"]), \
                 mock.patch.object(module, target, return_value={"success": True}) as install, self.quiet():
                self.assertEqual(backend.main(), 0)
                install.assert_called_once_with(confirm=True)

    def test_install_resolves_and_records_latest_immutable_selection_before_spawn(self):
        selection = (12345, "b12345", "a" * 40)
        state = Path(backend.engine_paths()["update"])
        def spawn_worker(args, **kwargs):
            saved = json.loads(state.read_text())
            self.assertEqual((saved["build"], saved["tag"], saved["commit"]), selection)
            self.assertEqual(args[1:], ["engine-install-run", selection[2]])
            return mock.Mock(pid=12345)
        with mock.patch.object(backend, "engine_info", return_value={"state": "not_installed"}), \
             mock.patch.object(backend, "newest_halo_tag", return_value=selection) as lookup, \
             mock.patch("subprocess.Popen", side_effect=spawn_worker):
            self.assertTrue(backend.start_engine_install()["success"])
        lookup.assert_called_once()
        self.assertEqual(json.loads(state.read_text())["commit"], selection[2])

    def test_install_lookup_failure_never_spawns_or_uses_cached_pin(self):
        for selection in (None, (12345, "b12345", "main")):
            with self.subTest(selection=selection), \
                 mock.patch.object(backend, "engine_info", return_value={"state": "not_installed"}), \
                 mock.patch.object(backend, "newest_halo_tag", return_value=selection), \
                 mock.patch("subprocess.Popen", return_value=mock.Mock(pid=12345)) as spawn:
                self.assertFalse(backend.start_engine_install()["success"])
                spawn.assert_not_called()

    def test_direct_install_worker_requires_and_preserves_immutable_commit(self):
        with mock.patch.object(backend, "engine_update_run", return_value=0) as worker:
            self.assertEqual(backend.engine_action("engine-install-run", "b" * 40), 0)
            worker.assert_called_once_with("b" * 40, first_install=True)

    def test_install_network_failure_or_timeout_does_not_spawn(self):
        cached = Path(backend.engine_paths()["check"])
        cached.parent.mkdir(parents=True)
        cached.write_text(json.dumps({"latest_build": 99999, "latest_commit": "f" * 40}))
        for response in (subprocess.CompletedProcess([], 128, "f" * 40 + "\trefs/tags/b99999\n"),
                         subprocess.TimeoutExpired("git", 25), OSError("git unavailable")):
            with self.subTest(response=response), \
                 mock.patch.object(backend, "engine_info", return_value={"state": "not_installed"}), \
                 mock.patch.object(backend, "newest_halo_tag", self.real_lookup), \
                 mock.patch("subprocess.run") as remote, \
                 mock.patch("subprocess.Popen") as spawn:
                if isinstance(response, Exception):
                    remote.side_effect = response
                else:
                    remote.return_value = response
                self.assertFalse(backend.start_engine_install()["success"])
                spawn.assert_not_called()

    def test_missing_git_can_resolve_exact_build_before_dependency_worker(self):
        refs = [{"ref": "refs/tags/b12345", "object": {"sha": "a" * 40, "type": "tag"}},
                {"ref": "refs/tags/b9", "object": {"sha": "b" * 40, "type": "commit"}}]
        peeled = {"object": {"sha": "c" * 40, "type": "commit"}}
        def response(url, **kwargs):
            self.assertTrue(url.startswith("https://api.github.com/repos/halo-box/strix-llama.cpp/git/"))
            body = peeled if "/git/tags/" in url else refs
            return contextlib.closing(io.BytesIO(json.dumps(body).encode()))
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("git")), \
             mock.patch("urllib.request.urlopen", side_effect=response):
            self.assertEqual(self.real_lookup(), (12345, "b12345", "c" * 40))

    def test_latest_annotated_tag_uses_peeled_commit_not_tag_object(self):
        output = ("a" * 40 + "\trefs/tags/b99\n" + "b" * 40 + "\trefs/tags/b100\n"
                  + "c" * 40 + "\trefs/tags/b100^{}\n")
        with mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, output)):
            self.assertEqual(self.real_lookup(), (100, "b100", "c" * 40))

    def test_unsupported_host_can_launch_install_but_cannot_start(self):
        with mock.patch.object(backend, "gpu_devices", return_value=[]), \
             mock.patch.object(backend, "engine_info", return_value={"state": "stopped"}), \
             mock.patch("subprocess.Popen") as spawn, \
             mock.patch.object(backend, "systemctl") as service:
            spawn.return_value.pid = 12345
            self.assertTrue(backend.start_engine_install()["success"])
            self.assertFalse(backend.start_engine()["success"])
            service.assert_not_called()

    def test_engine_hardware_support_is_live_not_install_record(self):
        record = Path(backend.engine_paths()["record"])
        record.parent.mkdir(parents=True)
        record.write_text('{"hardware_supported": true}')
        with mock.patch.object(backend, "gpu_devices", return_value=[]), \
             mock.patch.object(backend, "systemctl", return_value=(3, "inactive")), \
             mock.patch.object(backend, "port_open", return_value=False):
            self.assertFalse(backend.engine_info()["hardware_supported"])

    def test_unsupported_load_rejected_before_snapshot_or_router(self):
        with mock.patch("sys.argv", ["omastrix", "library-load", "test-model", "--confirm"]), \
             mock.patch.object(backend, "snapshot") as snapshot, \
             mock.patch.object(backend.library, "load_checked", return_value={"success": True}) as load, self.quiet():
            self.assertEqual(backend.main(), 1)
            snapshot.assert_not_called()
            load.assert_not_called()

    def test_webui_access_dispatch_preserves_mode_and_confirmation(self):
        for args, expected in (([], ("", False)), (["lan", "--confirm"], ("lan", True))):
            with self.subTest(args=args), \
                 mock.patch("sys.argv", ["omastrix", "webui-access", *args]), \
                 mock.patch.object(backend.webui, "set_access", create=True, return_value={"success": True}) as setter, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(backend.main(), 0)
                setter.assert_called_once_with(*expected)

    def test_launcher_spawn_failures_persist_with_cleared_pid(self):
        state = Path(backend.engine_paths()["update"])
        for launcher in (backend.start_engine_install, backend.start_engine_update):
            with self.subTest(launcher=launcher.__name__), \
                 mock.patch.object(backend, "engine_info", return_value={"state": "stopped"}), \
                 mock.patch.object(backend, "host_probe", return_value=(True,)), \
                 mock.patch.object(backend, "newest_halo_tag", return_value=(12345, "b12345", "a" * 40)), \
                 mock.patch.object(backend, "pid_alive", return_value=False), \
                 mock.patch("subprocess.Popen", side_effect=OSError("worker spawn failed")):
                state.parent.mkdir(parents=True, exist_ok=True)
                state.write_text('{"pid": 99999999, "error": "previous"}')
                result = launcher()
                self.assertFalse(result["success"])
                saved = json.loads(state.read_text())
                self.assertEqual(saved["pid"], 0)
                self.assertIn("worker spawn failed", saved["error"])

    def test_launcher_log_open_failures_persist_with_cleared_pid(self):
        state = Path(backend.engine_paths()["update"])
        log = Path(backend.engine_paths()["update_log"])
        log.mkdir(parents=True)
        for launcher in (backend.start_engine_install, backend.start_engine_update):
            with self.subTest(launcher=launcher.__name__), \
                 mock.patch.object(backend, "engine_info", return_value={"state": "stopped"}), \
                 mock.patch.object(backend, "host_probe", return_value=(True,)), \
                 mock.patch.object(backend, "newest_halo_tag", return_value=(12345, "b12345", "a" * 40)), \
                 mock.patch("subprocess.Popen") as spawn:
                result = launcher()
                self.assertFalse(result["success"])
                saved = json.loads(state.read_text())
                self.assertEqual(saved["pid"], 0)
                self.assertIn(str(log), saved["error"])
                spawn.assert_not_called()

    def test_launcher_failure_state_write_failure_preserves_previous_state(self):
        state = Path(backend.engine_paths()["update"])
        state.parent.mkdir(parents=True)
        previous = '{"pid": 0, "error": "previous valid failure"}'
        state.write_text(previous)
        with mock.patch.object(backend, "engine_info", return_value={"state": "stopped"}), \
             mock.patch.object(backend, "host_probe", return_value=(True,)), \
             mock.patch("subprocess.Popen", side_effect=OSError("spawn failed")), \
             mock.patch.object(backend.library.os, "replace", side_effect=OSError("state rename failed")):
            result = backend.start_engine_install()
        self.assertFalse(result["success"])
        self.assertIn("could not save failure state", result["error"])
        self.assertIn("state rename failed", result["error"])
        self.assertEqual(state.read_text(), previous)

    def test_malformed_local_engine_json_cannot_break_status(self):
        paths = backend.engine_paths()
        for key in ("record", "check", "update"):
            path = Path(paths[key])
            path.parent.mkdir(parents=True, exist_ok=True)
            for content in (b"null", b"[]", b"42", b'"text"', b"\xff",
                            b'{"version":[],"latest_build":{},"pid":true,"error":[]}'):
                with self.subTest(key=key, content=content), \
                     mock.patch.object(backend, "systemctl", return_value=(3, "inactive")), \
                     mock.patch.object(backend, "port_open", return_value=False):
                    path.write_bytes(content)
                    info = backend.engine_info()
                    self.assertIsInstance(info["version"], str)
                    self.assertIsInstance(info["latest_build"], int)
                    self.assertIsInstance(info["update_error"], str)
                    self.assertFalse(info["updating"])
            path.unlink()

    def test_worker_keeps_selected_build_tag_and_commit_after_completion(self):
        state = Path(backend.engine_paths()["update"])
        state.parent.mkdir(parents=True)
        selection = {"build": 12345, "tag": "b12345", "commit": "a" * 40}
        state.write_text(json.dumps(selection))
        with mock.patch.object(backend, "systemctl", return_value=(3, "inactive")), \
             mock.patch("subprocess.call", return_value=0):
            self.assertEqual(backend.engine_update_run(selection["commit"], first_install=True), 0)
        saved = json.loads(state.read_text())
        for key, value in selection.items():
            self.assertEqual(saved[key], value)

    def test_worker_rejects_missing_floating_or_extra_commit_arguments(self):
        for verb in ("engine-install-run", "engine-update-run"):
            for args in ([], [""], ["main"], ["b12345"], ["A" * 40], ["a" * 39],
                         ["a" * 40, "extra"]):
                with self.subTest(verb=verb, args=args), \
                     mock.patch("sys.argv", ["omastrix", verb, *args]), \
                     mock.patch.object(backend, "systemctl") as service, \
                     mock.patch("subprocess.call") as installer, self.quiet(), \
                     contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(backend.main(), 2)
                    service.assert_not_called()
                    installer.assert_not_called()

    def test_existing_engine_files_block_first_install_in_launcher_and_worker(self):
        for key in ("record", "bin"):
            path = Path(backend.engine_paths()[key])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("newer existing engine")
            try:
                with mock.patch.object(backend, "engine_info", return_value={"state": "not_installed"}), \
                     mock.patch.object(backend, "newest_halo_tag") as lookup, \
                     mock.patch("subprocess.Popen") as spawn, \
                     mock.patch("subprocess.call") as installer:
                    self.assertFalse(backend.start_engine_install()["success"])
                    self.assertEqual(backend.engine_update_run("a" * 40, first_install=True), 1)
                    lookup.assert_not_called()
                    spawn.assert_not_called()
                    installer.assert_not_called()
                self.assertEqual(path.read_text(), "newer existing engine")
            finally:
                path.unlink()

    def test_first_install_accepts_an_explicitly_missing_unit(self):
        def service(*args):
            if args[0] == "is-active":
                return 4, "inactive"
            if args[0] == "show":
                return 0, "LoadState=not-found\nActiveState=inactive"
            raise AssertionError(args)
        with mock.patch.object(backend, "systemctl", side_effect=service), \
             mock.patch.dict(backend.os.environ, {"OMASTRIX_TEST_SECRET": "not-for-builds"}), \
             mock.patch("subprocess.call", return_value=0) as installer:
            self.assertEqual(backend.engine_update_run("a" * 40, first_install=True), 0)
        installer.assert_called_once()
        self.assertFalse("OMASTRIX_TEST_SECRET" in installer.call_args.kwargs["env"])
        self.assertEqual(installer.call_args.args, ([backend.engine_paths()["installer"], "--first-install", "a" * 40],))
        lock_fd, = installer.call_args.kwargs["pass_fds"]
        self.assertEqual(installer.call_args.kwargs["env"]["OMASTRIX_ENGINE_LOCK_FD"], str(lock_fd))

    def test_missing_unit_exception_requires_exact_observed_properties(self):
        for code, body in (
            (1, "LoadState=not-found\nActiveState=inactive"),
            (0, "LoadState=loaded\nActiveState=inactive"),
            (0, "LoadState=not-found\nActiveState=activating"),
            (0, "LoadState=not-found\nActiveState=inactive\nActiveState=active"),
            (0, "LoadState=not-found"),
        ):
            def service(*args):
                return (4, "inactive") if args[0] == "is-active" else (code, body)
            with self.subTest(code=code, body=body), \
                 mock.patch.object(backend, "systemctl", side_effect=service), \
                 mock.patch("subprocess.call", return_value=0) as installer:
                self.assertNotEqual(backend.engine_update_run("a" * 40, first_install=True), 0)
                installer.assert_not_called()

    def test_update_refuses_a_missing_service(self):
        with mock.patch.object(backend, "systemctl", return_value=(4, "inactive")), \
             mock.patch("subprocess.call", return_value=0) as installer:
            self.assertNotEqual(backend.engine_update_run("a" * 40), 0)
        installer.assert_not_called()

    def test_failed_engine_check_returns_a_nonzero_exit(self):
        output = io.StringIO()
        with mock.patch.object(backend, "engine_info", return_value={}), \
             mock.patch.object(backend, "newest_halo_tag", return_value=None), \
             contextlib.redirect_stdout(output):
            result = backend.engine_action("engine-check", "")
        self.assertNotEqual(result, 0)
        self.assertFalse(json.loads(output.getvalue())["success"])
