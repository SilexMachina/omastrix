"""Isolated regressions for the four library review findings."""
import configparser
import copy
import fcntl
import json
import subprocess
from pathlib import Path
from unittest import mock

from test_backend_safety import IsolatedBackend, library


class PresetPublicationTests(IsolatedBackend):
    def test_publication_rejects_symlink_destination_and_ancestors(self):
        for component in (".config", ".config/omastrix", ".config/omastrix/models.ini"):
            with self.subTest(component=component):
                outside = self.home / "outside"
                outside.mkdir(exist_ok=True)
                sentinel = outside / "models.ini"
                sentinel.write_text("untouched\n")
                link = self.home / component
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(sentinel if link.name == "models.ini" else outside)
                try:
                    with self.assertRaises((OSError, ValueError)):
                        library.write_preset(110)
                    self.assertTrue(link.is_symlink())
                    self.assertEqual(sentinel.read_text(), "untouched\n")
                    self.assertEqual(list(outside.iterdir()), [sentinel])
                finally:
                    link.unlink()

    def test_ancestor_swap_during_publication_cannot_redirect_write(self):
        path = Path(library.preset_path())
        path.parent.mkdir(parents=True)
        path.write_text("old complete preset\n")
        outside = self.home / "outside"
        outside.mkdir()
        sentinel = outside / path.name
        sentinel.write_text("untouched\n")
        pinned = path.parent.with_name("pinned")
        replace = library.os.replace

        def swap_ancestor(source, destination, **kwargs):
            self.assertEqual(path.read_text(), "old complete preset\n")
            path.parent.rename(pinned)
            path.parent.symlink_to(outside)
            return replace(source, destination, **kwargs)

        expected = library.preset_text(110)
        with mock.patch.object(library.os, "replace", side_effect=swap_ancestor):
            library.write_preset(110)
        self.assertEqual(sentinel.read_text(), "untouched\n")
        self.assertEqual((pinned / path.name).read_text(), expected)
        self.assertEqual(list(pinned.iterdir()), [pinned / path.name])

    def test_failed_publication_preserves_complete_old_preset(self):
        path = Path(library.preset_path())
        path.parent.mkdir(parents=True)
        path.write_text("old complete preset\n")
        with mock.patch.object(library.os, "replace", side_effect=OSError("publication failed")):
            with self.assertRaisesRegex(OSError, "publication failed"):
                library.write_preset(110)
        self.assertEqual(path.read_text(), "old complete preset\n")
        self.assertEqual(list(path.parent.iterdir()), [path])


class EngineLoadLockTests(IsolatedBackend):
    def test_load_refuses_engine_install_lock_before_autostart(self):
        self.file()
        lock = self.home / ".local/state/omastrix/engine.lock"
        lock.parent.mkdir(parents=True)
        with lock.open("a") as fh, \
             mock.patch.object(library, "server_list", return_value=None) as router, \
             mock.patch.object(library, "ensure_engine", return_value=(False, "unexpected start")) as start:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = library.load_checked(self.row["id"], 110, True)
        self.assertFalse(result["success"])
        self.assertIn("engine operation", result["error"])
        router.assert_not_called()
        start.assert_not_called()

    def test_load_holds_engine_guard_through_model_request(self):
        self.file()
        observed = []

        def request(*args, **kwargs):
            lock = self.home / ".local/state/omastrix/engine.lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            with lock.open("a") as fh:
                try:
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    observed.append("locked")
                else:
                    observed.append("unlocked")
            return {}

        with mock.patch.object(library, "server_list", side_effect=[
                {self.row["name"]: "unloaded"}, {self.row["name"]: "unloaded"},
                {self.row["name"]: "loaded"}]), \
             mock.patch.object(library, "write_preset"), \
             mock.patch.object(library, "http_json", side_effect=request):
            self.assertTrue(library.load_checked(self.row["id"], 110, True)["success"])
        self.assertEqual(observed, ["locked"])


class RouterIdentityTests(IsolatedBackend):
    def setUp(self):
        super().setUp()
        self.row["name"] = "model"
        self.row["added"] = True
        self.other = copy.deepcopy(self.row)
        self.other["id"] = "other-model"
        self.other["files"][0]["path"] = "other/model.gguf"
        self.rows = [self.row, self.other]
        patcher = mock.patch.object(library, "all_models", return_value=(self.rows, 14))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.file()
        path = Path(library.dest_for(self.other["files"][0]["path"]))
        path.parent.mkdir(parents=True)
        path.write_bytes(b"GGUF")

    def legacy_preset(self, row):
        path = Path(library.preset_path())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("version = 1\n\n[%s]\nmodel = %s\nctx-size = 8192\n" % (
            row["name"], library.dest_for(row["files"][0]["path"])))

    def test_same_basename_links_produce_distinct_id_presets(self):
        with mock.patch.object(library, "load_catalog", return_value=([], 14)), \
             mock.patch.object(library, "remote_size", return_value=4):
            for host in ("one.example", "two.example"):
                self.assertTrue(library.add_from_url("https://" + host + "/model.gguf")["success"])
        self.rows[:] = library.load_added()
        for row in self.rows:
            path = Path(library.dest_for(row["files"][0]["path"]))
            path.parent.mkdir(parents=True)
            path.write_bytes(b"GGUF")
        text = library.preset_text(110)
        for row in self.rows:
            self.assertIn("[%s]" % row["id"], text)
        self.assertNotIn("[model]", text)
        # Strict parser catches the original duplicate [model] regression too.
        configparser.ConfigParser(interpolation=None).read_string("[header]\n" + text)

    def test_load_targets_selected_id_not_shared_display_name(self):
        server = {row["id"]: "unloaded" for row in self.rows}
        requested = []
        def request(path, **kwargs):
            name = library.urllib.parse.parse_qs(library.urllib.parse.urlsplit(path).query)["model"][0]
            requested.append(name)
            server[name] = "loaded"
            return {}
        with mock.patch.object(library, "server_list", side_effect=lambda: dict(server)), \
             mock.patch.object(library, "http_json", side_effect=request), \
             mock.patch.object(library, "reload_server") as reload:
            self.assertTrue(library.load_checked(self.other["id"], 110, True)["success"])
        self.assertEqual(requested, [self.other["id"]])
        reload.assert_not_called()

    def test_loaded_status_and_counters_use_id_not_shared_name(self):
        with mock.patch.object(library, "server_list", return_value={self.other["id"]: "loaded"}), \
             mock.patch.object(library, "recommend_id", return_value=self.row["id"]), \
             mock.patch.object(library, "slot_state", return_value=True) as slots, \
             mock.patch.object(library, "token_count", return_value=23) as tokens, \
             mock.patch.object(library, "service_ram_gb", return_value=2):
            view = library.library_view(110)
        self.assertEqual(view["loaded_id"], self.other["id"])
        self.assertEqual([row["id"] for row in view["rows"] if row["server_status"] == "loaded"], [self.other["id"]])
        slots.assert_called_once_with(self.other["id"])
        tokens.assert_called_once_with(self.other["id"])
        self.assertEqual(view["tokens_since_load"], 23)

    def test_unload_targets_selected_id(self):
        with mock.patch.object(library, "server_list", return_value={self.other["id"]: "loaded"}), \
             mock.patch.object(library, "unload_name", return_value={}) as unload, \
             mock.patch.object(library, "wait_unloaded", return_value=True) as wait:
            self.assertTrue(library.unload_model(self.other["id"])["success"])
        unload.assert_called_once_with(self.other["id"])
        wait.assert_called_once_with(self.other["id"])

    def test_fetch_refuses_weights_loaded_by_id(self):
        with mock.patch.object(library, "server_list", return_value={self.row["id"]: "loaded"}), self.quiet():
            result = library.fetch(self.row["id"])
        self.assertEqual(result, 1)
        self.assertEqual(self.file().read_bytes(), b"GGUF")

    def test_delete_waits_for_selected_id_before_removing_weights(self):
        with mock.patch.object(library, "server_list", return_value={self.other["id"]: "loaded"}), \
             mock.patch.object(library, "unload_name", return_value={}) as unload, \
             mock.patch.object(library, "wait_unloaded", return_value=False) as wait:
            result = library.delete_model(self.other["id"], 110, True)
        self.assertFalse(result["success"])
        unload.assert_called_once_with(self.other["id"])
        wait.assert_called_once_with(self.other["id"])
        self.assertTrue(Path(library.dest_for(self.other["files"][0]["path"])).exists())

    def test_deleting_idle_duplicate_never_unloads_active_id(self):
        with mock.patch.object(library, "server_list", return_value={self.other["id"]: "loaded"}), \
             mock.patch.object(library, "unload_name") as unload, \
             mock.patch.object(library, "reload_server") as reload:
            result = library.delete_model(self.row["id"], 110, True)
        self.assertTrue(result["success"])
        unload.assert_not_called()
        reload.assert_not_called()
        self.assertTrue(Path(library.dest_for(self.other["files"][0]["path"])).exists())

    def test_unique_legacy_active_model_is_preserved_without_reload(self):
        self.rows[:] = [self.row]
        self.row.pop("added")
        self.row["name"] = "Qwen legacy 35B"
        self.legacy_preset(self.row)
        with mock.patch.object(library, "server_list", return_value={self.row["name"]: "loaded"}), \
             mock.patch.object(library, "http_json") as request, \
             mock.patch.object(library, "reload_server") as reload, \
             mock.patch.object(library, "unload_name") as unload, \
             mock.patch.object(library, "recommend_id", return_value=self.row["id"]), \
             mock.patch.object(library, "slot_state", return_value=False) as slots, \
             mock.patch.object(library, "token_count", return_value=12) as tokens, \
             mock.patch.object(library, "service_ram_gb", return_value=1):
            for _ in range(2):
                view = library.library_view(110)
                library.write_preset(110)
                self.assertEqual(view["loaded_id"], self.row["id"])
                self.assertIn("[%s]" % self.row["name"], Path(library.preset_path()).read_text())
            self.assertTrue(library.load_checked(self.row["id"], 110, False)["success"])
        request.assert_not_called()
        reload.assert_not_called()
        unload.assert_not_called()
        self.assertEqual(slots.call_args.args, (self.row["name"],))
        self.assertEqual(tokens.call_args.args, (self.row["name"],))

    def test_existing_legacy_binding_is_not_reassigned_when_name_collides(self):
        self.legacy_preset(self.other)
        with mock.patch.object(library, "server_list", return_value={"model": "loaded"}), \
             mock.patch.object(library, "recommend_id", return_value=self.row["id"]), \
             mock.patch.object(library, "slot_state", return_value=False), \
             mock.patch.object(library, "token_count", return_value=1), \
             mock.patch.object(library, "service_ram_gb", return_value=1), \
             mock.patch.object(library, "reload_server") as reload, \
             mock.patch.object(library, "http_json") as request:
            library.write_preset(110)
            view = library.library_view(110)
            result = library.load_checked(self.row["id"], 110, False)
        self.assertEqual(view["loaded_id"], self.other["id"])
        self.assertFalse(result["success"])
        self.assertTrue(result.get("needs_confirm"))
        reload.assert_not_called()
        request.assert_not_called()

    def test_ambiguous_legacy_download_and_delete_fail_closed(self):
        for action in (lambda: library.fetch(self.row["id"]),
                       lambda: library.delete_model(self.row["id"], 110, True)):
            with mock.patch.object(library, "server_list", return_value={"model": "loaded"}), self.quiet():
                result = action()
            self.assertTrue(result == 1 if isinstance(result, int) else not result["success"])
            self.assertTrue(Path(library.dest_for(self.row["files"][0]["path"])).exists())


class DeleteStateGuardTests(IsolatedBackend):
    def test_selected_loaded_route_is_unloaded_even_when_another_is_first(self):
        path = self.file()
        for route in (self.row["id"], self.row["name"]):
            with self.subTest(route=route), \
                 mock.patch.object(library, "server_list", return_value={
                     "unrelated-model": "loaded", route: "loaded"}), \
                 mock.patch.object(library, "unload_name", return_value={}) as unload, \
                 mock.patch.object(library, "wait_unloaded", return_value=False) as wait:
                result = library.delete_model(self.row["id"], 110, True)
            self.assertFalse(result["success"])
            unload.assert_called_once_with(route)
            wait.assert_called_once_with(route)
            self.assertEqual(path.read_bytes(), b"GGUF")

    def test_failed_service_probe_never_authorizes_deletion(self):
        path = self.file()
        for code in (1, 4):
            for stdout in ("inactive\n", "failed\n"):
                with self.subTest(code=code, stdout=stdout), \
                     mock.patch.object(library, "server_list", return_value=None), \
                     mock.patch.object(library.subprocess, "run", return_value=
                                       subprocess.CompletedProcess([], code, stdout, "probe failed")):
                    result = library.delete_model(self.row["id"], 110, True)
                self.assertFalse(result["success"])
                self.assertIn("Cannot confirm engine state", result["error"])
                self.assertEqual(path.read_bytes(), b"GGUF")


class DownloadDeletePolicyTests(IsolatedBackend):
    def test_delete_refuses_active_download_even_when_mutation_lock_is_free(self):
        path = self.file()
        library.write_download_state(self.row["id"], {"pid": 12345, "error": "keep state"})
        for confirm in (False, True):
            with self.subTest(confirm=confirm), \
                 mock.patch.object(library, "pid_alive", return_value=True), \
                 mock.patch.object(library, "server_list", return_value={}) as router:
                result = library.delete_model(self.row["id"], 110, confirm)
            self.assertFalse(result["success"])
            self.assertNotIn("needs_confirm", result)
            self.assertIn("wait", result["error"].lower())
            self.assertIn("download", result["error"].lower())
            router.assert_not_called()
            self.assertTrue(path.exists())
            self.assertEqual(json.loads(Path(library.download_path(self.row["id"])).read_text())["pid"], 12345)

    def test_download_locked_delete_never_cancels_or_removes_files(self):
        path = self.file()
        lock = self.home / ".local/state/omastrix/downloads.lock"
        lock.parent.mkdir(parents=True)
        with lock.open("a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = library.delete_model(self.row["id"], 110, True)
        self.assertFalse(result["success"])
        self.assertIn("downloads", result["error"])
        self.assertTrue(path.exists())

    def test_active_download_is_not_advertised_as_deletable(self):
        self.file()
        with mock.patch.object(library, "download_state", return_value={"running": True}), \
             mock.patch.object(library, "server_list", return_value={}), \
             mock.patch.object(library, "recommend_id", return_value=self.row["id"]):
            self.assertFalse(library.library_view(110)["rows"][0]["deletable"])
