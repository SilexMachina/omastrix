"""Snapshot isolation and read-only hardware discovery contracts."""
import contextlib
from unittest import mock

from test_backend_safety import IsolatedBackend, backend


class SnapshotTests(IsolatedBackend):
    def snapshot_dependencies(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        values = (
            (backend, "host_probe", ("/fake/gpu", {"DRIVER": "amdgpu"}, "1002:1586", "0000:01:00.0", "Strix Halo", True)),
            (backend, "mem_total_bytes", 128 * 1024**3),
            (backend, "read_int", 96 * 1024**3),
            (backend, "pages_limit", None),
            (backend, "configured_pages", None),
            (backend, "engine_info", {"state": "stopped"}),
            (backend, "webui_info", {"state": "stopped"}),
            (backend, "read_json", {"version": "0.5.0"}),
            (backend.library, "library_view", {"rows": [], "generating": False}),
            (backend.library, "write_preset", None),
        )
        mocks = {}
        for module, name, value in values:
            mocks[name] = stack.enter_context(mock.patch.object(module, name, return_value=value))
        stack.enter_context(mock.patch("plugin_update.status", return_value={}))
        return mocks

    def test_cached_hardware_name_is_reused_but_actions_probe_live(self):
        uevent = "DRIVER=amdgpu\nPCI_ID=1002:1586\nPCI_SLOT_NAME=0000:01:00.0\n"
        with mock.patch.object(backend, "gpu_devices", return_value=["/fake/gpu"]), \
             mock.patch.object(backend, "read_text", return_value=uevent), \
             mock.patch.object(backend, "lspci_name", return_value="AMD Strix Halo") as lookup:
            self.assertTrue(backend.host_probe(cached=True)[-1])
            self.assertTrue(backend.host_probe(cached=True)[-1])
            lookup.assert_called_once()
            backend.host_probe()
            self.assertEqual(lookup.call_count, 2)

    def test_snapshot_reuses_hardware_result_for_engine_status(self):
        mocks = self.snapshot_dependencies()
        backend.snapshot()
        mocks["host_probe"].assert_called_once()
        mocks["engine_info"].assert_called_once_with(hardware_supported=True)

    def test_snapshot_has_one_gtt_choice_field_and_memory_requirements(self):
        self.snapshot_dependencies()
        result = backend.snapshot()
        self.assertNotIn("supported_gtt", result)
        self.assertEqual(result["gtt_choices"], ["64", "96", "110"])
        self.assertEqual(result["gtt_requirements"]["110"], 124)

    def test_webui_update_dispatch_preserves_dependency_approval(self):
        for confirmed in (False, True):
            for verb, function, args, response in (
                ('webui-update', 'start_update', [], {'success': True}),
                ('webui-update-run', 'update_run', ['0.14.0'], 0),
            ):
                argv = ['omastrix', verb] + args + (['--confirm'] if confirmed else [])
                with self.subTest(verb=verb, confirmed=confirmed), mock.patch('sys.argv', argv), \
                     mock.patch.object(backend.webui, function, return_value=response) as action, \
                     mock.patch.object(backend, 'snapshot', side_effect=AssertionError('Unexpected snapshot')), self.quiet():
                    self.assertEqual(backend.main(), 0)
                    action.assert_called_once_with(*args, confirm=confirmed)

    def test_explicit_verification_dispatch_does_not_need_engine_or_snapshot(self):
        for verb, function, response in (("library-verify", "start_verify", {"success": True}),
                                         ("library-verify-run", "verify", 0)):
            with self.subTest(verb=verb), mock.patch("sys.argv", ["omastrix", verb, "fixture-model"]), \
                 mock.patch.object(backend.library, function, return_value=response) as action, \
                 mock.patch.object(backend, "snapshot", side_effect=AssertionError("Unexpected snapshot")), \
                 mock.patch.object(backend, "host_probe", side_effect=AssertionError("Unexpected hardware probe")), self.quiet():
                self.assertEqual(backend.main(), 0)
                action.assert_called_once_with("fixture-model")

    def test_malformed_library_state_stays_scoped(self):
        mocks = self.snapshot_dependencies()
        for error in (KeyError("models"), TypeError("Invalid model record"), AttributeError("Invalid job state")):
            with self.subTest(error=type(error).__name__):
                mocks["library_view"].side_effect = error
                result = backend.snapshot()
                self.assertEqual(result["engine"]["state"], "stopped")
                self.assertTrue(result["library"]["error"])
                mocks["write_preset"].assert_not_called()

    def test_library_failure_does_not_hide_engine_or_webui(self):
        mocks = self.snapshot_dependencies()
        mocks["library_view"].side_effect = ValueError("Storage unavailable")
        result = backend.snapshot()
        self.assertEqual(result["engine"]["state"], "stopped")
        self.assertEqual(result["webui"]["state"], "stopped")
        self.assertEqual(result["library"]["rows"], [])
        self.assertIn("Storage unavailable", result["library"]["error"])
        mocks["write_preset"].assert_not_called()
