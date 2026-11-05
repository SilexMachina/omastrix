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
        self.assertEqual(installer.call_args.args, ([backend.engine_paths()["installer"]],))
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
