"""Backend regressions. All state is temporary; external actions are mocked."""
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))
import library
import webui

loader = importlib.machinery.SourceFileLoader("omastrix_backend", str(BIN / "omastrix"))
spec = importlib.util.spec_from_loader(loader.name, loader)
backend = importlib.util.module_from_spec(spec)
loader.exec_module(backend)


class IsolatedBackend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        # Any unanticipated process or HTTP operation fails rather than touching the host.
        for target in ("subprocess.run", "subprocess.call", "subprocess.Popen", "urllib.request.urlopen", "os.kill", "os.killpg"):
            patcher = mock.patch(target, side_effect=AssertionError("Unmocked external action: " + target))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.row = {
            "id": "test-model", "name": "Test model", "short": "Test", "quant": "Q4",
            "tags": [], "ctx": 8192, "kv_gib": 1, "serve": {},
            "files": [{"path": "test/model.gguf", "bytes": 4,
                       "sha256": hashlib.sha256(b"GGUF").hexdigest(),
                       "url": "https://example.org/model.gguf", "primary": True}],
        }
        patcher = mock.patch.object(library, "all_models", return_value=([self.row], 14))
        patcher.start()
        self.addCleanup(patcher.stop)

    def file(self, content=b"GGUF"):
        path = self.home / "models/test/model.gguf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def quiet(self):
        return contextlib.redirect_stdout(io.StringIO())


class DownloadIntegrityTests(IsolatedBackend):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(library, "server_list", return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_delete_cannot_remove_files_while_download_worker_owns_them(self):
        nested = []
        def download(cmd, **kwargs):
            partial = Path(cmd[cmd.index("-o") + 1])
            partial.write_bytes(b"GGUF")
            nested.append(library.delete_model(self.row["id"], 110, True))
            self.assertTrue(partial.exists())
            return subprocess.CompletedProcess(cmd, 0)
        with mock.patch("subprocess.run", side_effect=download), \
             mock.patch.object(library, "pid_alive", return_value=False), \
             mock.patch.object(library, "server_list", return_value={}), \
             mock.patch.object(library, "write_preset"), \
             mock.patch.object(library, "reload_server"), self.quiet():
            self.assertEqual(library.fetch(self.row["id"]), 0)
        self.assertFalse(nested[0]["success"])
        self.assertEqual((self.home / "models/test/model.gguf").read_bytes(), b"GGUF")

    def test_fetch_does_not_claim_success_when_added_hash_cannot_be_saved(self):
        self.row["files"][0]["sha256"] = ""
        self.file()
        with mock.patch.object(library, "save_added", side_effect=OSError("disk full")), \
             mock.patch.object(library, "load_added", return_value=[self.row]), self.quiet():
            self.assertEqual(library.fetch(self.row["id"]), 1)
        self.assertIn("disk full", library.download_state(self.row["id"])["error"])

    def test_download_curl_forbids_config_injection_and_non_https_redirects(self):
        def download(cmd, **kwargs):
            self.assertEqual(cmd[1], "-q")
            self.assertEqual(cmd[cmd.index("--proto") + 1], "=https")
            self.assertEqual(cmd[cmd.index("--proto-redir") + 1], "=https")
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"GGUF")
            return subprocess.CompletedProcess(cmd, 0)
        with mock.patch("subprocess.run", side_effect=download), self.quiet():
            self.assertEqual(library.fetch(self.row["id"]), 0)

    def test_concurrent_download_requests_launch_only_one_worker(self):
        nested = []
        def spawn(*args, **kwargs):
            if not nested:
                nested.append(None)
                nested[0] = library.start_download(self.row["id"])
            return mock.Mock(pid=12345)
        with mock.patch("subprocess.Popen", side_effect=spawn) as launch:
            self.assertTrue(library.start_download(self.row["id"])["success"])
        self.assertEqual(launch.call_count, 1)
        self.assertFalse(nested[0]["success"])

    def test_install_does_not_skip_verification_of_existing_sized_file(self):
        self.file(b"BAD!")
        with mock.patch("subprocess.Popen", return_value=mock.Mock(pid=12345)) as spawn:
            result = library.start_download(self.row["id"])
            self.assertTrue(result["success"])
            self.assertEqual(result["message"], "Downloading Test model into ~/models.")
        spawn.assert_called_once()

    def test_fetch_rejects_same_size_corruption(self):
        self.file(b"BAD!")
        with self.quiet():
            code = library.fetch(self.row["id"])
        self.assertEqual(code, 1)
        self.assertIn("hash", library.download_state(self.row["id"])["error"].lower())
        self.assertFalse(library.row_files(self.row)[0][0]["ready"])

    def test_download_is_not_installed_until_hash_verified(self):
        def download(cmd, **kwargs):
            dest = Path(cmd[cmd.index("-o") + 1])
            dest.write_bytes(b"BAD!")
            self.assertFalse(library.row_files(self.row)[0][0]["ready"])
            return subprocess.CompletedProcess(cmd, 0)
        with mock.patch("subprocess.run", side_effect=download), self.quiet():
            self.assertEqual(library.fetch(self.row["id"]), 1)
        self.assertFalse(library.row_files(self.row)[0][0]["ready"])


class PathSafetyTests(IsolatedBackend):
    def test_concurrent_add_requests_cannot_overwrite_each_other(self):
        nested = []
        def size(url):
            if not nested:
                nested.append(None)
                nested[0] = library.add_from_url("https://example.org/other.gguf")
            return 4
        with mock.patch.object(library, "load_catalog", return_value=([], 14)), \
             mock.patch.object(library, "remote_size", side_effect=size):
            result = library.add_from_url("https://example.org/first.gguf")
        self.assertTrue(result["success"])
        self.assertFalse(nested[0]["success"])
        self.assertEqual([row["id"] for row in library.load_added()], [result["id"]])

    def test_recording_download_hash_cannot_race_a_new_link(self):
        library.save_added([self.row])
        save = library.save_added
        nested = []
        def save_with_concurrent_add(rows):
            if not nested:
                nested.append(None)
                nested[0] = library.add_from_url("https://example.org/other.gguf")
            save(rows)
        with mock.patch.object(library, "load_catalog", return_value=([], 14)), \
             mock.patch.object(library, "remote_size", return_value=4), \
             mock.patch.object(library, "save_added", side_effect=save_with_concurrent_add):
            library.remember_added_file(self.row["id"], self.row["files"][0]["path"], 4, "verified")
        self.assertFalse(nested[0]["success"])
        self.assertEqual(library.load_added()[0]["files"][0]["sha256"], "verified")

    def test_malformed_url_returns_validation_error(self):
        try:
            normalized, error = library.normalize_gguf_url("https://[invalid/model.gguf")
        except ValueError:
            self.fail("Malformed URLs must return a validation error")
        self.assertFalse(normalized)
        self.assertTrue(error)

    def test_added_filename_is_decoded_and_keeps_gguf_suffix_when_truncated(self):
        with mock.patch.object(library, "load_catalog", return_value=([], 14)), \
             mock.patch.object(library, "remote_size", return_value=4):
            for filename in ("A" * 200 + ".gguf", "%41" * 60 + ".gguf"):
                with self.subTest(filename=filename):
                    result = library.add_from_url("https://example.org/" + filename)
                    self.assertTrue(result["success"])
                    row = next(row for row in library.load_added() if row["id"] == result["id"])
                    saved = Path(row["files"][0]["path"]).name
                    self.assertTrue(saved.endswith(".gguf"))
                    self.assertLessEqual(len(saved), 180)
                    self.assertNotIn("_41", saved)

    def test_url_validation_rejects_projectors_and_encoded_split_shards(self):
        for url in ("https://example.org/mmproj-model.gguf",
                    "https://example.org/model-%30%30%30%30%31-of-00002.gguf",
                    "https://example.org/model-00001-OF-00002.gguf"):
            with self.subTest(url=url):
                normalized, error = library.normalize_gguf_url(url)
                self.assertFalse(normalized)
                self.assertTrue(error)

    def test_url_normalization_preserves_signed_query_and_checks_hf_hostname(self):
        for url in ("https://example.org/model.gguf?signature=abc",
                    "https://nothuggingface.co/a/blob/main/model.gguf"):
            with self.subTest(url=url):
                self.assertEqual(library.normalize_gguf_url(url), (url, ""))

    def test_download_state_ids_cannot_escape_the_state_directory(self):
        for model_id in ("../outside", str(self.home / "absolute"), "", "nested/id"):
            with self.subTest(model_id=model_id), self.assertRaises(ValueError):
                library.write_download_state(model_id, {"pid": 0})

    def test_models_root_symlink_cannot_redirect_downloads_or_deletions(self):
        outside = self.home / "unrelated-models"
        outside.mkdir()
        (self.home / "models").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            library.dest_for("test/model.gguf")

    def test_model_paths_reject_aliases_and_symlinks(self):
        target = self.file()
        (target.parent / "alias.gguf").symlink_to(target)
        for rel in ("", ".", str(target), "test/../test/model.gguf", "test/alias.gguf"):
            with self.subTest(path=rel), self.assertRaises(ValueError):
                library.dest_for(rel)


class RouterSafetyTests(IsolatedBackend):
    def test_model_polls_always_disable_autoload(self):
        name = "Model & other/name"
        with mock.patch.object(library, "http_json", return_value=[]) as request:
            self.assertFalse(library.slot_state(name))
        path = request.call_args.args[0]
        query = library.urllib.parse.parse_qs(library.urllib.parse.urlsplit(path).query)
        self.assertEqual(query, {"autoload": ["false"], "model": [name]})
        with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(b"tokens_predicted_total 12\n")) as request:
            self.assertEqual(library.token_count(name), 12)
        query = library.urllib.parse.parse_qs(library.urllib.parse.urlsplit(request.call_args.args[0]).query)
        self.assertEqual(query, {"autoload": ["false"], "model": [name]})

    def test_valid_pinned_router_inventory_preserves_exact_states(self):
        rows = [{"id": name, "status": {"value": state}} for name, state in
                (("Idle", "unloaded"), ("Busy", "loaded"), ("Starting", "loading"), ("Stopping", "unloading"))]
        with mock.patch.object(library, "http_json", return_value={"data": rows}):
            self.assertEqual(library.server_list(), {row["id"]: row["status"]["value"] for row in rows})

    def test_malformed_router_inventory_is_never_interpreted_as_unloaded(self):
        payloads = ({"data": None}, {"data": {}}, {"data": [{"id": "Test model"}]},
                    {"data": [{"id": "Test model", "status": {"value": "unknown"}}]},
                    {"data": [{"id": "", "status": {"value": "unloaded"}}]}, [])
        for payload in payloads:
            with self.subTest(payload=payload), mock.patch.object(library, "http_json", return_value=payload):
                self.assertIsNone(library.server_list())

    def test_load_refuses_transitional_router_before_any_autoload_request(self):
        self.file()
        for state in ("loading", "unloading"):
            with self.subTest(state=state), \
                 mock.patch.object(library, "server_list", return_value={"Other": state}), \
                 mock.patch.object(library, "write_preset"), \
                 mock.patch.object(library, "reload_server"), \
                 mock.patch.object(library, "http_json", return_value={}) as request:
                self.assertFalse(library.load_checked(self.row["id"], 110, True)["success"])
                request.assert_not_called()

    def test_fetch_never_removes_weights_in_use_by_the_router(self):
        path = self.file(b"BAD!")
        for state in ("loaded", "loading", "unloading"):
            path.write_bytes(b"BAD!")
            with self.subTest(state=state), \
                 mock.patch.object(library, "server_list", return_value={self.row["name"]: state}), self.quiet():
                self.assertEqual(library.fetch(self.row["id"]), 1)
                self.assertTrue(path.exists())
                self.assertIn("unload", library.download_state(self.row["id"])["error"].lower())

    def test_load_cannot_race_download_publication(self):
        import fcntl
        lock = self.home / ".local/state/omastrix/downloads.lock"
        lock.parent.mkdir(parents=True)
        self.file()
        with lock.open("a") as fh, mock.patch.object(library, "server_list", return_value={}) as router:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = library.load_checked(self.row["id"], 110, True)
        self.assertFalse(result["success"])
        router.assert_not_called()
        self.assertIn("operation", result["error"])

    def test_delete_refuses_unknown_or_transitional_model_state(self):
        path = self.file()
        for server in (None, {self.row["name"]: "loading"}, {self.row["name"]: "unloading"}):
            self.file()
            with self.subTest(server=server), \
                 mock.patch.object(library, "server_list", return_value=server), \
                 mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "active", "")), \
                 mock.patch.object(library, "write_preset"), \
                 mock.patch.object(library, "reload_server", return_value={}):
                self.assertFalse(library.delete_model(self.row["id"], 110, True)["success"])
                self.assertTrue(path.exists())

    def test_delete_removes_owned_partial_but_keeps_projector(self):
        complete = self.file()
        partial = complete.with_name(complete.name + ".part")
        complete.rename(partial)
        projector = partial.parent / "mmproj.gguf"
        projector.write_bytes(b"keep")
        with mock.patch.object(library, "server_list", return_value={}), \
             mock.patch.object(library, "write_preset"), \
             mock.patch.object(library, "reload_server", return_value={}):
            result = library.delete_model(self.row["id"], 110, True)
        self.assertTrue(result["success"])
        self.assertEqual(result["removed"], 1)
        self.assertFalse(partial.exists())
        self.assertTrue(projector.exists())

    def test_router_mutations_are_serialized(self):
        self.file()
        nested = []
        def unload(name):
            nested.append(library.load_checked(self.row["id"], 110, True))
            return {}
        with mock.patch.object(library, "server_list", return_value={self.row["name"]: "loaded"}), \
             mock.patch.object(library, "unload_name", side_effect=unload), \
             mock.patch.object(library, "wait_unloaded", return_value=True), \
             mock.patch.object(library, "write_preset"), \
             mock.patch.object(library, "http_json", return_value={}):
            self.assertTrue(library.unload_model(self.row["id"])["success"])
        self.assertFalse(nested[0]["success"])
        self.assertIn("operation", nested[0]["error"])

    def test_load_reports_failure_if_router_did_not_load_requested_model(self):
        self.file()
        with mock.patch.object(library, "server_list", return_value={self.row["name"]: "unloaded"}), \
             mock.patch.object(library, "write_preset"), \
             mock.patch.object(library, "http_json", return_value={}):
            self.assertFalse(library.load_checked(self.row["id"], 110, True)["success"])

    def test_load_rejects_same_size_corruption_before_touching_router(self):
        self.file(b"BAD!")
        with mock.patch.object(library, "server_list", return_value={self.row["name"]: "unloaded"}) as server, \
             mock.patch.object(library, "write_preset"), \
             mock.patch.object(library, "http_json", return_value={}) as request:
            result = library.load_checked(self.row["id"], 110, True)
        self.assertFalse(result["success"])
        self.assertIn("hash", result["error"].lower())
        server.assert_not_called()
        request.assert_not_called()

    def test_switch_aborts_when_previous_model_does_not_unload(self):
        self.file()
        for unloaded in ({"error": "busy"}, {}):
            with self.subTest(response=unloaded), \
                 mock.patch.object(library, "server_list", return_value={"Other": "loaded"}), \
                 mock.patch.object(library, "unload_name", return_value=unloaded), \
                 mock.patch.object(library, "wait_unloaded", return_value=False), \
                 mock.patch.object(library, "write_preset"), \
                 mock.patch.object(library, "reload_server"), \
                 mock.patch.object(library, "http_json", return_value={}) as request:
                self.assertFalse(library.load_checked(self.row["id"], 110, True)["success"])
                request.assert_not_called()

    def test_unload_wait_fails_closed_on_unreachable_or_transitional_router(self):
        for state in (None, {"Test model": "loading"}, {"Test model": "unloading"}):
            with self.subTest(state=state), \
                 mock.patch.object(library, "server_list", return_value=state), \
                 mock.patch.object(library.time, "monotonic", side_effect=[0, 0, 2]), \
                 mock.patch.object(library.time, "sleep"):
                self.assertFalse(library.wait_unloaded("Test model", timeout=1))

    def test_delete_waits_for_router_to_release_weights(self):
        path = self.file()
        with mock.patch.object(library, "server_list", return_value={self.row["name"]: "loaded"}), \
             mock.patch.object(library, "unload_name", return_value={}), \
             mock.patch.object(library, "wait_unloaded", return_value=False) as wait, \
             mock.patch.object(library, "write_preset"):
            result = library.delete_model(self.row["id"], 110, True)
        self.assertFalse(result["success"])
        wait.assert_called_once_with(self.row["name"])
        self.assertTrue(path.exists())


class HostSafetyTests(IsolatedBackend):
    def test_failed_boot_rebuild_restores_gtt_files_and_modes(self):
        limine = self.home / "limine.conf"
        modprobe = self.home / "modprobe.conf"
        limine.write_bytes(b"# original boot config\n")
        limine.chmod(0o640)
        with mock.patch.object(backend, "LIMINE_CONF", str(limine)), \
             mock.patch.object(backend, "MODPROBE_CONF", str(modprobe)), \
             mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "rebuild failed")), \
             self.quiet():
            self.assertEqual(backend.write_gtt("64"), 1)
        self.assertEqual(limine.read_bytes(), b"# original boot config\n")
        self.assertEqual(limine.stat().st_mode & 0o777, 0o640)
        self.assertFalse(modprobe.exists())

    def test_snapshot_exposes_supported_gtt_with_amdgpu_requirement(self):
        for driver, expected in (("amdgpu", ["64"]), ("vfio-pci", [])):
            with self.subTest(driver=driver), \
                 mock.patch.object(backend, "gpu_devices", return_value=["/mock/gpu"]), \
                 mock.patch.object(backend, "read_text", return_value="PCI_ID=1002:1586\nDRIVER=" + driver), \
                 mock.patch.object(backend, "read_int", return_value=64 * 1024**3), \
                 mock.patch.object(backend, "lspci_name", return_value="Strix Halo"), \
                 mock.patch.object(backend, "mem_total_bytes", return_value=96 * 1024**3), \
                 mock.patch.object(library, "library_view", return_value={}), \
                 mock.patch.object(library, "write_preset"), \
                 mock.patch.object(backend, "engine_info", return_value={}), \
                 mock.patch.object(backend, "webui_info", return_value={}), \
                 mock.patch.object(backend, "read_json", return_value={"version": "0.5.0"}):
                snap = backend.snapshot()
                self.assertEqual(snap.get("gtt_choices"), expected)
                self.assertEqual(snap.get("app_version"), "0.5.0")
                self.assertEqual(snap.get("supported_gtt"), expected)
                self.assertEqual(snap["strix_halo"], driver == "amdgpu")

    def test_set_gtt_refuses_unsupported_choice_before_privilege_escalation(self):
        with mock.patch.object(sys, "argv", [str(BIN / "omastrix"), "set-gtt", "110"]), \
             mock.patch.object(backend, "snapshot", return_value={"strix_halo": True, "supported_gtt": ["64"]}), \
             mock.patch.object(backend, "gpu_devices", return_value=[]), \
             mock.patch.object(os, "execvp") as escalate, \
             mock.patch.object(backend, "write_gtt") as write, self.quiet():
            self.assertEqual(backend.main(), 1)
            escalate.assert_not_called()
            write.assert_not_called()

    def test_supported_gtt_choices_reserve_real_memtotal(self):
        self.assertTrue(hasattr(backend, "supported_gtt_choices"), "GTT choices need host-aware filtering")
        for total, halo, expected in ((128, True, ["64", "96", "110"]),
                                      (64, True, []), (96, True, ["64"]),
                                      (128, False, []), (None, True, [])):
            with self.subTest(total=total, halo=halo):
                self.assertEqual(backend.supported_gtt_choices(halo, None if total is None else total * 1024**3), expected)


class EngineInstallTests(IsolatedBackend):
    def test_engine_start_cannot_race_an_install_worker(self):
        nested = []
        def service(*args):
            return (3, "inactive") if args[0] == "is-active" else (0, "")
        def install(*args, **kwargs):
            with self.quiet():
                nested.append(backend.engine_action("engine-start", ""))
            return 0
        with mock.patch.object(backend, "systemctl", side_effect=service) as systemctl, \
             mock.patch("subprocess.call", side_effect=install):
            self.assertEqual(backend.engine_update_run("a" * 40), 0)
        self.assertEqual(nested, [1])
        self.assertFalse(any(call.args[0] == "start" for call in systemctl.call_args_list))

    def test_engine_worker_refuses_unknown_or_failed_service_probe(self):
        for code, state in ((4, "unknown"), (1, "inactive"), (1, "failed")):
            with self.subTest(code=code, state=state), \
                 mock.patch.object(backend, "systemctl", return_value=(code, state)), \
                 mock.patch("subprocess.call", return_value=0) as install:
                self.assertEqual(backend.engine_update_run("a" * 40), 1)
                install.assert_not_called()

    def test_update_launchers_refuse_unavailable_or_transitional_state_before_network(self):
        for state in ("unavailable", "starting", "stopping"):
            with self.subTest(state=state), \
                 mock.patch.object(backend, "engine_info", return_value={"state": state}), \
                 mock.patch.object(webui, "status", return_value={"state": state, "running": False}), \
                 mock.patch.object(backend, "newest_halo_tag") as engine_check, \
                 mock.patch.object(webui, "latest_release") as webui_check:
                self.assertFalse(backend.start_engine_update()["success"])
                self.assertFalse(webui.start_update()["success"])
                engine_check.assert_not_called()
                webui_check.assert_not_called()

    def test_failed_remote_listing_does_not_offer_partial_tag_output(self):
        partial = "a" * 40 + "\trefs/tags/b99999\n"
        with mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 128, partial, "network failure")):
            self.assertIsNone(backend.newest_halo_tag())

    def test_first_install_refuses_existing_record_or_broken_wrapper(self):
        paths = backend.engine_paths()
        record = Path(paths["record"])
        wrapper = Path(paths["bin"])
        record.parent.mkdir(parents=True)
        wrapper.parent.mkdir(parents=True)
        for artifact in (record, wrapper):
            record.unlink(missing_ok=True)
            wrapper.unlink(missing_ok=True)
            Path(paths["update"]).unlink(missing_ok=True)
            with self.subTest(artifact=artifact):
                if artifact == record:
                    record.write_text('{"version":"build 12297"}')
                else:
                    wrapper.symlink_to(wrapper.parent / "missing")
                with mock.patch.object(backend, "engine_info", return_value={"installed": False}), \
                     mock.patch.object(backend, "host_probe", return_value=("", {}, "", "", "", True)), \
                     mock.patch.object(backend, "systemctl", return_value=(3, "inactive")), \
                     mock.patch("subprocess.Popen", return_value=mock.Mock(pid=12345)) as launch, \
                     mock.patch("subprocess.call", return_value=0) as install:
                    self.assertFalse(backend.start_engine_install()["success"])
                    self.assertEqual(backend.engine_action("engine-install-run", ""), 1)
                    launch.assert_not_called()
                    install.assert_not_called()
                artifact.unlink()

    def test_fresh_worker_uses_installer_default_pin_and_no_update_override(self):
        with mock.patch.object(backend, "systemctl", return_value=(3, "inactive")), \
             mock.patch("subprocess.call", return_value=0) as install:
            self.assertEqual(backend.engine_action("engine-install-run", ""), 0)
        self.assertEqual(install.call_count, 1)
        self.assertEqual(install.call_args.args, ([backend.engine_paths()["installer"]],))
        self.assertTrue(install.call_args.kwargs.get("pass_fds"))

    def test_concurrent_install_requests_launch_only_one_worker(self):
        nested = []
        def spawn(*args, **kwargs):
            if not nested:
                nested.append(None)
                nested[0] = backend.start_engine_install()
            return mock.Mock(pid=12345)
        with mock.patch.object(backend, "engine_info", return_value={"installed": False}), \
             mock.patch.object(backend, "host_probe", return_value=("", {}, "", "", "", True)), \
             mock.patch("subprocess.Popen", side_effect=spawn) as launch:
            self.assertTrue(backend.start_engine_install()["success"])
        self.assertEqual(launch.call_count, 1)
        self.assertFalse(nested[0]["success"])

    def test_worker_refuses_active_or_activating_service(self):
        for state in ("active", "activating", "deactivating"):
            with self.subTest(state=state), \
                 mock.patch.object(backend, "systemctl", return_value=(0, state)), \
                 mock.patch("subprocess.call", return_value=0) as install:
                self.assertEqual(backend.engine_update_run("a" * 40), 1)
                install.assert_not_called()
                self.assertIn("Stop", backend.read_json(backend.engine_paths()["update"])["error"])

    def test_engine_install_is_async_and_uses_shared_update_state(self):
        with mock.patch.object(sys, "argv", [str(BIN / "omastrix"), "engine-install"]), \
             mock.patch.object(backend, "engine_info", return_value={"installed": False, "state": "not_installed"}), \
             mock.patch.object(backend, "host_probe", return_value=("", {}, "", "", "", True)), \
             mock.patch("subprocess.Popen", return_value=mock.Mock(pid=12345)) as spawn, self.quiet():
            self.assertEqual(backend.main(), 0)
        spawn.assert_called_once()
        self.assertEqual(spawn.call_args.args[0][1:], ["engine-install-run"])
        state = backend.read_json(backend.engine_paths()["update"])
        self.assertEqual(state["pid"], 12345)
        self.assertEqual(state["error"], "")


class CommandContractTests(IsolatedBackend):
    def test_update_messages_state_only_the_requested_action(self):
        with mock.patch.object(backend, "engine_info", return_value={"version": "build 1", "state": "stopped"}), \
             mock.patch.object(backend, "newest_halo_tag", return_value=(2, "b2", "a" * 40)), \
             mock.patch.object(webui, "status", return_value={"running": False, "state": "stopped"}), \
             mock.patch.object(webui, "latest_release", return_value=("1.2.3", "")), \
             mock.patch.object(webui, "version_of", return_value="1.2.2"), \
             mock.patch.object(webui, "find_uv", return_value="/mock/uv"), \
             mock.patch("subprocess.Popen", return_value=mock.Mock(pid=12345)):
            self.assertEqual(backend.start_engine_update()["message"], "Updating strix-llama.cpp to build 2.")
            self.assertEqual(webui.start_update()["message"], "Updating Open WebUI to 1.2.3.")

    def test_failed_actions_have_nonzero_exit_and_explicit_json_result(self):
        cases = (("library-add", library, "add_from_url"),
                 ("library-download", library, "start_download"),
                 ("library-load", library, "load_checked"),
                 ("library-unload", library, "unload_model"),
                 ("library-delete", library, "delete_model"),
                 ("webui-install", webui, "start_install"),
                 ("webui-start", webui, "start"), ("webui-stop", webui, "stop"),
                 ("webui-check", webui, "check"), ("webui-update", webui, "start_update"),
                 ("engine-update", backend, "start_engine_update"))
        for verb, module, method in cases:
            with self.subTest(verb=verb), \
                 mock.patch.object(sys, "argv", [str(BIN / "omastrix"), verb, "test-model"]), \
                 mock.patch.object(backend, "snapshot", return_value={"gtt_total_gib": 110}), \
                 mock.patch.object(backend, "host_probe", return_value=("", {}, "", "", "", True)), \
                 mock.patch.object(module, method, return_value={"success": False, "error": "Refused"}), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(backend.main(), 1)
                self.assertIs(json.loads(output.getvalue())["success"], False)


class WebuiSafetyTests(IsolatedBackend):
    def test_update_worker_refuses_unknown_or_failed_service_probe(self):
        for code, state in ((4, "unknown"), (1, "inactive"), (1, "failed")):
            with self.subTest(code=code, state=state), \
                 mock.patch.object(webui, "systemctl", return_value=(code, state)), \
                 mock.patch.object(webui, "find_uv", return_value="/mock/uv"), \
                 mock.patch.object(os, "access", return_value=True), \
                 mock.patch("subprocess.call", return_value=0) as pip, \
                 mock.patch.object(webui, "ensure_layout"):
                self.assertEqual(webui.update_run("1.2.3"), 1)
                pip.assert_not_called()

    def test_status_does_not_report_unknown_or_transitional_service_as_stopped(self):
        for code, text, expected in ((1, "Failed to connect to bus", "unavailable"),
                                     (4, "unknown", "unavailable"),
                                     (0, "activating", "starting"),
                                     (0, "deactivating", "stopping")):
            with self.subTest(text=text), \
                 mock.patch.object(backend, "systemctl", return_value=(code, text)), \
                 mock.patch.object(webui, "systemctl", return_value=(code, text)), \
                 mock.patch.object(backend, "port_open", return_value=False), \
                 mock.patch.object(backend, "host_probe", return_value=("", {}, "", "", "", True)), \
                 mock.patch.object(webui, "port_open", return_value=False), \
                 mock.patch.object(webui, "version_of", return_value="1.2.3"), \
                 mock.patch.object(os.path, "isfile", return_value=True), \
                 mock.patch.object(os, "access", return_value=True):
                self.assertEqual(backend.engine_info()["state"], expected)
                self.assertEqual(webui.status()["state"], expected)

    def test_layout_publication_does_not_follow_wrapper_or_unit_symlinks(self):
        for publish, path in ((webui.write_wrapper, webui.wrapper_path()), (webui.write_unit, webui.unit_path())):
            with self.subTest(path=path):
                target = self.home / (Path(path).name + ".unrelated")
                target.write_text("keep")
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                Path(path).symlink_to(target)
                with mock.patch.object(webui, "systemctl", return_value=(0, "")):
                    publish()
                self.assertEqual(target.read_text(), "keep")
                self.assertFalse(Path(path).is_symlink())

    def test_failed_daemon_reload_cannot_produce_install_success(self):
        def service(*args):
            return (3, "inactive") if args[0] == "is-active" else (1, "reload failed")
        with mock.patch.object(webui, "current_venv", return_value="/mock/venv"), \
             mock.patch.object(webui, "systemctl", side_effect=service), self.quiet():
            self.assertEqual(webui.install(), 1)
        self.assertIn("reload failed", webui.read_json(webui.install_state_path())["error"])

    def test_webui_start_cannot_race_an_update_worker(self):
        nested = []
        def package(*args, **kwargs):
            nested.append(webui.start())
            return str(self.home / "staged-venv")
        with mock.patch.object(webui, "systemctl", return_value=(3, "inactive")), \
             mock.patch.object(webui, "find_uv", return_value="/mock/uv"), \
             mock.patch.object(os, "access", return_value=True), \
             mock.patch.object(webui, "port_open", return_value=True), \
             mock.patch.object(webui, "promote"), \
             mock.patch.object(webui, "build_venv", side_effect=package):
            self.assertEqual(webui.update_run("1.2.3"), 0)
        self.assertFalse(nested[0]["success"])
        self.assertIn("operation", nested[0]["error"])

    def test_install_messages_name_missing_dependency_and_omit_reassurances(self):
        with mock.patch.object(webui, "find_uv", return_value=""), \
             mock.patch.object(os, "access", return_value=False):
            self.assertEqual(webui.start_install()["error"], "Open WebUI installation requires uv.")
        with mock.patch.object(webui, "find_uv", return_value="/mock/uv"), \
             mock.patch.object(os, "access", return_value=False), \
             mock.patch("subprocess.Popen", return_value=mock.Mock(pid=12345)):
            self.assertEqual(webui.start_install()["message"], "Installing Open WebUI.")

    def test_env_quotes_data_directory_as_one_shell_assignment(self):
        home = self.home / "space $(do-not-run)"
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            webui.write_env()
            env = Path(webui.env_path())
            data_line = next(line for line in env.read_text().splitlines() if line.startswith("DATA_DIR="))
            self.assertEqual(shlex.split(data_line), ["DATA_DIR=" + str(home / ".local/share/omastrix/webui/data")])
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)

    def test_concurrent_installs_launch_only_one_worker(self):
        nested = []
        def spawn(*args, **kwargs):
            if not nested:
                nested.append(None)
                nested[0] = webui.start_install()
            return mock.Mock(pid=12345)
        with mock.patch.object(webui, "find_uv", return_value="/mock/uv"), \
             mock.patch.object(os, "access", return_value=False), \
             mock.patch("subprocess.Popen", side_effect=spawn) as launch:
            self.assertTrue(webui.start_install()["success"])
        self.assertEqual(launch.call_count, 1)
        self.assertFalse(nested[0]["success"])

    def test_update_worker_rechecks_service_before_package_replacement(self):
        with mock.patch.object(webui, "systemctl", return_value=(0, "active")), \
             mock.patch.object(webui, "find_uv", return_value="/mock/uv"), \
             mock.patch.object(os, "access", return_value=True), \
             mock.patch("subprocess.call", return_value=0) as pip, \
             mock.patch.object(webui, "ensure_layout"):
            self.assertEqual(webui.update_run("1.2.3"), 1)
            pip.assert_not_called()
            self.assertIn("Stop", webui.read_json(webui.update_state_path())["error"])


class LibraryViewTests(IsolatedBackend):
    def test_unknown_fit_is_not_reported_as_zero_shortfall(self):
        with mock.patch.object(library, "server_list", return_value={}), \
             mock.patch.object(library, "recommend_id", return_value=self.row["id"]):
            row = library.library_view(None)["rows"][0]
        self.assertFalse(row["fits"])
        self.assertEqual(row["notes"], "GTT ceiling unavailable")

    def test_parameter_labels_do_not_invent_total_counts(self):
        self.row["id"] = "qwen38-flash-next"
        with mock.patch.object(library, "server_list", return_value={}), \
             mock.patch.object(library, "recommend_id", return_value=self.row["id"]):
            self.assertEqual(library.library_view(110)["rows"][0]["params"], "—")
            self.row["parameter_count"] = 176943899520
            self.assertEqual(library.library_view(110)["rows"][0]["params"], "177B")
            self.row["parameters"] = "123B total / 4B active"
            self.assertEqual(library.library_view(110)["rows"][0]["params"], "123B total / 4B active")

    def test_binary_memory_units_are_gib_and_snapshot_does_not_hash_weights(self):
        self.file()
        with mock.patch.object(library, "server_list", return_value={self.row["name"]: "loaded"}), \
             mock.patch.object(library, "recommend_id", return_value=self.row["id"]), \
             mock.patch.object(library, "slot_state", return_value=False), \
             mock.patch.object(library, "token_count", return_value=None), \
             mock.patch.object(library, "service_ram_gb", return_value=16.4), \
             mock.patch.object(library, "sha256_file", side_effect=AssertionError("Snapshot must not hash weights")):
            row = library.library_view(110)["rows"][0]
        self.assertEqual(row["ram"], "16.4 GiB")
        self.assertTrue(row["size"].endswith(" GiB"))


class StateSafetyTests(IsolatedBackend):
    def test_worker_spawn_errors_are_persisted_instead_of_crashing(self):
        cases = ((library.fetch, (self.row["id"],), lambda: library.download_state(self.row["id"])),
                 (backend.engine_update_run, ("a" * 40,), lambda: backend.read_json(backend.engine_paths()["update"])),
                 (webui.install, (), lambda: webui.read_json(webui.install_state_path())),
                 (webui.update_run, ("1.2.3",), lambda: webui.read_json(webui.update_state_path())))
        for worker, args, state in cases:
            with self.subTest(worker=worker.__name__), \
                 mock.patch.object(library, "server_list", return_value={}), \
                 mock.patch.object(backend, "systemctl", return_value=(3, "inactive")), \
                 mock.patch.object(webui, "systemctl", return_value=(3, "inactive")), \
                 mock.patch.object(webui, "find_uv", return_value="/missing/uv"), \
                 mock.patch.object(os, "access", return_value=True), \
                 mock.patch("subprocess.call", side_effect=FileNotFoundError("missing executable")), \
                 mock.patch("subprocess.run", side_effect=FileNotFoundError("missing executable")), \
                 self.quiet():
                # WebUI install must enter its package steps rather than its installed shortcut.
                with mock.patch.object(webui, "webui_bin", return_value="/not-installed/open-webui"), \
                     mock.patch.object(os, "access", side_effect=lambda path, mode: str(path) != "/not-installed/open-webui"):
                    self.assertEqual(worker(*args), 1)
                self.assertEqual(state().get("pid"), 0)
                self.assertIn("missing executable", state().get("error", ""))

    def test_failed_state_write_preserves_previous_json(self):
        library.write_download_state(self.row["id"], {"pid": 0, "error": "Previous error"})
        with mock.patch.object(json, "dump", side_effect=OSError("disk full")), self.assertRaises(OSError):
            library.write_download_state(self.row["id"], {"pid": 123, "error": ""})
        self.assertEqual(library.download_state(self.row["id"]).get("error"), "Previous error")


if __name__ == "__main__":
    unittest.main()
