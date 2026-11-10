"""Read-only status probes with synthetic router responses only."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))
import library

loader = importlib.machinery.SourceFileLoader("model_status_backend", str(BIN / "omastrix"))
spec = importlib.util.spec_from_loader(loader.name, loader)
backend = importlib.util.module_from_spec(spec)
loader.exec_module(backend)


def models(*entries):
    return {"data": [{"id": name, "status": {"value": state}} for name, state in entries]}


class ModelStatusTests(unittest.TestCase):
    def setUp(self):
        for target in ("subprocess.run", "subprocess.call", "subprocess.Popen",
                       "urllib.request.urlopen", "builtins.open", "os.kill", "os.killpg"):
            patcher = mock.patch(target, side_effect=AssertionError("Unexpected action: " + target))
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(library, "http_json")
        self.http = patcher.start()
        self.addCleanup(patcher.stop)

    def test_no_loaded_models_is_empty_without_slots(self):
        for response in (models(), models(("sample", "unloaded")),
                         models(("sample", "loading")), models(("sample", "unloading"))):
            with self.subTest(response=response):
                self.http.reset_mock()
                self.http.return_value = response
                self.assertEqual(library.model_status(), {"state": "empty"})
                self.http.assert_called_once_with("/models")

    def test_uncataloged_alias_transitions_active_ready_empty(self):
        alias = "outside/catalog & sample+?雪"
        path = "/slots?autoload=false&model=outside%2Fcatalog%20%26%20sample%2B%3F%E9%9B%AA"
        for slots, expected in (([{"is_processing": True}], "active"),
                                ([{"is_processing": False}], "ready"), ([], "ready")):
            with self.subTest(slots=slots):
                self.http.reset_mock()
                self.http.side_effect = [models((alias, "loaded")), slots]
                self.assertEqual(library.model_status(), {"state": expected})
                self.assertEqual(self.http.call_args_list,
                                 [mock.call("/models"), mock.call(path, timeout=1)])
        self.http.side_effect = [models((alias, "unloaded"))]
        self.assertEqual(library.model_status(), {"state": "empty"})

    def test_malformed_or_unavailable_router_is_unknown(self):
        for response in (None, [], {}, {"error": "unavailable"}, {"data": {}},
                         {"data": [None]}, {"data": [{"id": "sample"}]},
                         models(("sample", "other")), models(("", "loaded")),
                         models(("sample", "loaded"), ("sample", "loaded"))):
            with self.subTest(response=response):
                self.http.reset_mock()
                self.http.return_value = response
                self.assertEqual(library.model_status(), {"state": "unknown"})
                self.http.assert_called_once_with("/models")

    def test_malformed_or_unavailable_slots_never_claim_ready(self):
        for slots in (None, {}, {"error": "unavailable"}, "bad", [None], [{}],
                      [{"is_processing": value} for value in (False, None)],
                      *([{"is_processing": value}] for value in (0, 1, "false", "true", [], {}))):
            with self.subTest(slots=slots):
                self.http.side_effect = [models(("sample", "loaded")), slots]
                self.assertEqual(library.model_status(), {"state": "unknown"})

    def test_multiple_loaded_active_wins_otherwise_unknown_wins(self):
        idle = [{"is_processing": False}]
        active = [{"is_processing": True}]
        unknown = [{}]
        for first, second, expected in ((idle, active, "active"), (unknown, active, "active"),
                                        (unknown, idle, "unknown"), (idle, unknown, "unknown"),
                                        (idle, [], "ready"), (active, unknown, "active")):
            with self.subTest(first=first, second=second):
                self.http.side_effect = [models(("one", "loaded"), ("two", "loaded")), first, second]
                self.assertEqual(library.model_status(), {"state": expected})
        self.http.side_effect = [models(("sample", "loaded")), [{}, {"is_processing": True}]]
        self.assertEqual(library.model_status(), {"state": "active"})

    def test_cli_emits_state_before_any_snapshot_or_hardware_probe(self):
        for state, responses in (("empty", [models()]),
                                 ("ready", [models(("sample", "loaded")), []]),
                                 ("active", [models(("sample", "loaded")), [{"is_processing": True}]]),
                                 ("unknown", [{"error": "unavailable"}])):
            with self.subTest(state=state), \
                 mock.patch.object(sys, "argv", ["omastrix", "model-status"]), \
                 mock.patch.object(backend, "host_probe", side_effect=AssertionError("Hardware probe")), \
                 mock.patch.object(backend, "snapshot", side_effect=AssertionError("Snapshot")):
                self.http.side_effect = responses
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(backend.main(), 0)
                self.assertEqual(json.loads(output.getvalue()), {"state": state})
                self.assertEqual(len(output.getvalue().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
