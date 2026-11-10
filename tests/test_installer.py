"""Installer safety tests: fake HOME and mocked tools, never real installs/services."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT / "engine-pin.json").read_text())


class InstallerProcessSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.tools = self.home / "tools"
        self.tools.mkdir()
        self.repo = self.home / "plugin"
        (self.repo / "bin").mkdir(parents=True)
        self.installer = self.repo / "bin/omastrix-engine-install"
        shutil.copy2(ROOT / "bin/omastrix-engine-install", self.installer)
        shutil.copy2(ROOT / "bin/omastrix", self.repo / "bin/omastrix")
        self.device = self.home / "sys/class/drm/card0/device"
        self.device.mkdir(parents=True)
        (self.device / "uevent").write_text("DRIVER=amdgpu\nPCI_ID=1002:1586\n")
        (self.device / "mem_info_gtt_total").write_text(str(96 * 1024**3))
        fixture = self.home / "fixture"
        fixture.mkdir()
        (fixture / "sitecustomize.py").write_text('''import glob
from pathlib import Path
real_glob, real_path_glob = glob.glob, Path.glob
def isolated_glob(pattern, *args, **kwargs):
    if str(pattern).startswith("/sys/class/drm/"):
        pattern = str(Path.home()) + str(pattern)
    return real_glob(pattern, *args, **kwargs)
def isolated_path_glob(path, pattern, *args, **kwargs):
    if str(path) == "/sys/class/drm":
        path = Path.home() / "sys/class/drm"
    return real_path_glob(path, pattern, *args, **kwargs)
glob.glob, Path.glob = isolated_glob, isolated_path_glob
''')
        python = self.tools / "python3"
        python.write_text(f'#!/bin/sh\nexport PYTHONPATH="{fixture}"\nexec "{sys.executable}" "$@"\n')
        python.chmod(0o755)
        (self.repo / "engine-pin.json").write_text(json.dumps(PIN))
        self.log = self.home / "commands.jsonl"
        self.control = self.home / "control.json"
        icd = self.home / "radeon_icd.x86_64.json"
        icd.write_text(json.dumps({"ICD": {"library_path": "libvulkan_radeon.so"}}))
        self.extra_env = {"OMASTRIX_RADV_ICD": str(icd), "PYTHONPATH": str(fixture)}
        self.settings: dict[str, object] = {"state": "inactive", "devices": "Vulkan0: AMD Radeon 8060S (RADV STRIX_HALO) (98304 MiB, 96000 MiB free)", "version": "version: b12297 (6994643)"}
        # All tools capable of changing services, fetching, building, or installing
        # are fake executables. Only filesystem writes inside this HOME are real.
        stub = f'''#!{sys.executable}
import json, os, sys
from pathlib import Path
name, args = Path(sys.argv[0]).name, sys.argv[1:]
os.environ.setdefault("CONTROL", str(Path.home() / "control.json"))
os.environ.setdefault("COMMAND_LOG", str(Path.home() / "commands.jsonl"))
settings = json.loads(Path(os.environ["CONTROL"]).read_text())
with open(os.environ["COMMAND_LOG"], "a") as out:
    out.write(json.dumps([name] + args) + "\\n")
if name == "systemctl":
    if "is-active" in args:
        print(settings["state"])
        sys.exit(3 if settings["state"] == "inactive" else 0)
    if "show" in args:
        if settings.get("service_error"): sys.exit(1)
        print("LoadState=" + settings.get("load_state", "loaded"))
        if settings["state"] != "unknown": print("ActiveState=" + settings["state"])
        print("SubState=" + ("running" if settings["state"] == "active" else "dead"))
    if "daemon-reload" in args: sys.exit(settings.get("reload_code", 0))
    sys.exit(0)
if name == "git":
    if "clone" in args:
        source = Path(args[-1]); (source / ".git").mkdir(parents=True)
    if "rev-parse" in args: print(settings.get("actual_commit", "{PIN['commit']}"))
    sys.exit(0)
if name == "cmake":
    import fcntl
    with (Path.home() / ".local/state/omastrix/engine.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            sys.exit("Engine lock was not held during build")
    if "--build" in args:
        target = Path(args[args.index("--build")+1]) / "bin"
        target.mkdir(parents=True, exist_ok=True)
        body = {('#!' + sys.executable + chr(10))!r} + 'import json,os,sys\\nfrom pathlib import Path\\nc=json.loads(Path(os.environ.get("CONTROL", str(Path.home() / "control.json"))).read_text())\\nprint(c["version"] if "--version" in sys.argv else c["devices"])\\nsys.exit(c.get("version_code",0) if "--version" in sys.argv else c.get("verify_code",0))\\n'
        for tool in ("llama-server", "llama-cli", "llama-bench"):
            p = target / tool; p.write_text(body); p.chmod(0o755)
    if settings.get("start_during_build") and "--build" in args:
        settings["state"] = "active"
        Path(os.environ["CONTROL"]).write_text(json.dumps(settings))
    sys.exit(settings.get("build_code", 0))
sys.exit(0)
'''
        for name in ("git", "cmake", "systemctl", "ninja", "c++", "cc", "glslc", "pkg-config", "pacman", "lspci"):
            path = self.tools / name
            path.write_text(stub)
            path.chmod(0o755)

    def run_installer(self, *args):
        self.control.write_text(json.dumps(self.settings))
        return subprocess.run(
            [str(self.installer), *args], capture_output=True, text=True,
            env={**os.environ, "HOME": str(self.home), "COMMAND_LOG": str(self.log),
                 "CONTROL": str(self.control), **getattr(self, "extra_env", {}), "PATH": getattr(self, "path", str(self.tools) + os.pathsep + os.environ["PATH"])},
            timeout=10, pass_fds=getattr(self, "pass_fds", ()),
        )

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def assert_no_build(self):
        self.assertFalse(any(row[0] in ("git", "cmake") for row in self.commands()))

    def test_explicit_first_install_builds_selected_commit_not_pin(self):
        selected = "b" * 40
        self.settings["actual_commit"] = selected
        result = self.run_installer("--first-install", selected)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = json.loads((self.home / ".config/omastrix/engine.json").read_text())
        self.assertEqual(record["commit"], selected)
        self.assertTrue(any("fetch" in row and row[-1] == selected for row in self.commands()))

    def test_unsupported_host_installs_native_build_without_radv_acceptance(self):
        (self.device / "uevent").write_text("DRIVER=i915\nPCI_ID=8086:1234\n")
        self.extra_env["OMASTRIX_RADV_ICD"] = str(self.home / "missing-icd.json")
        self.settings.update(devices="CPU only", verify_code=1)
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = json.loads((self.home / ".config/omastrix/engine.json").read_text())
        self.assertEqual(record["hardware_acceptance"], "skipped_unsupported_host")
        self.assertTrue(any("-DGGML_VULKAN=ON" in row for row in self.commands()))
        self.assertEqual(record["commit"], PIN["commit"])
        self.assertEqual(record["version"], "b12297 (6994643)")

    def test_unsupported_update_and_failed_version_still_enforce_verification(self):
        shutil.rmtree(self.device)
        self.extra_env["OMASTRIX_RADV_ICD"] = str(self.home / "absent.json")
        self.settings["version_code"] = 1
        result = self.run_installer(PIN["commit"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("version verification failed", result.stderr.lower())
        self.assertFalse((self.home / ".config/omastrix/engine.json").exists())
        self.settings["version_code"] = 0
        result = self.run_installer(PIN["commit"])
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads((self.home / ".config/omastrix/engine.json").read_text())
        self.assertEqual(record["hardware_acceptance"], "skipped_unsupported_host")

    def test_supported_host_cannot_skip_radv_via_environment(self):
        self.extra_env.update(OMASTRIX_RADV_ICD=str(self.home / "absent.json"),
                              OMASTRIX_ALLOW_UNSUPPORTED="1", OMASTRIX_HARDWARE_SUPPORTED="no")
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RADV ICD", result.stderr)
        self.assert_no_build()

    def test_wrappers_reprobe_current_host_and_only_allow_version_on_unsupported(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.home / ".config/omastrix/engine.json").read_text())["hardware_acceptance"], "verified_strix_radv_heap")
        # Runtime protection must survive removal of the plugin checkout.
        shutil.rmtree(self.repo)
        (self.device / "uevent").write_text("DRIVER=amdgpu\nPCI_ID=1002:744c\n")
        env = {**os.environ, **self.extra_env, "HOME": str(self.home),
               "CONTROL": str(self.control), "PATH": str(self.tools) + os.pathsep + os.environ["PATH"],
               "OMASTRIX_ALLOW_UNSUPPORTED": "1", "OMASTRIX_HARDWARE_SUPPORTED": "yes"}
        for tool in ("llama-server", "llama-cli", "llama-bench"):
            wrapper = self.home / ".local/share/omastrix/bin" / tool
            for args in ([], ["--host", "127.0.0.1"], ["--version", "--model", "ignored.gguf"]):
                probe = subprocess.run([str(wrapper), *args], env=env, capture_output=True, text=True, timeout=5)
                self.assertNotEqual(probe.returncode, 0, probe.stdout)
                self.assertIn("unsupported", probe.stderr.lower())
            probe = subprocess.run([str(wrapper), "--version"], env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(probe.returncode, 0, probe.stderr)
        unit = (self.home / ".config/systemd/user/omastrix-llama.service").read_text()
        self.assertIn("ExecStart=%h/.local/share/omastrix/bin/llama-server ", unit)

    def test_symlinked_install_directories_are_refused_without_external_writes(self):
        for relative in (".local/share/omastrix", ".local/share/omastrix/bin",
                         ".local/share/omastrix/src", ".local/state/omastrix",
                         ".config/omastrix", ".config/systemd", ".config/systemd/user"):
            with self.subTest(relative=relative):
                link = self.home / relative
                target = self.home / "unrelated-directory"
                target.mkdir(exist_ok=True)
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(target, target_is_directory=True)
                try:
                    result = self.run_installer(PIN["commit"])
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertEqual(list(target.iterdir()), [])
                    self.assert_no_build()
                finally:
                    link.unlink()
                    for directory in (self.home / ".local", self.home / ".config", target):
                        if directory.exists():
                            shutil.rmtree(directory)
                    self.log.unlink(missing_ok=True)

    def test_running_service_is_refused_before_git_or_build(self):
        self.settings["state"] = "active"
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_build()
        self.assertIn("stop", result.stderr.lower())
        self.assertFalse((self.home / ".config/omastrix/engine.json").exists())

    def test_malformed_or_unloadable_service_state_is_refused(self):
        for state, load in (("inactive", "error"), ("inactive-extra", "loaded"),
                            ("inactive\nActiveState=active", "loaded")):
            with self.subTest(state=state, load=load):
                self.settings.update(state=state, load_state=load)
                self.log.unlink(missing_ok=True)
                result = self.run_installer(PIN["commit"])
                self.assertNotEqual(result.returncode, 0)
                self.assert_no_build()
                self.assertNotIn("INSTALL_OK", result.stdout)

    def test_unknown_service_state_is_refused_before_git_or_build(self):
        self.settings["state"] = "unknown"
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_build()
        self.assertIn("stopped", result.stderr.lower())


    def test_explicit_first_install_protects_existing_newer_or_broken_files(self):
        for relative in (".config/omastrix/engine.json", ".local/share/omastrix/bin/llama-server"):
            for broken in (False, True):
                with self.subTest(relative=relative, broken=broken):
                    path = self.home / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if broken:
                        path.symlink_to(self.home / "missing-newer-engine")
                    else:
                        path.write_text('{"version": "build 99999", "commit": "newer"}')
                    try:
                        result = self.run_installer("--first-install", "a" * 40)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("already installed", result.stderr.lower())
                        self.assert_no_build()
                        if broken:
                            self.assertTrue(path.is_symlink())
                        else:
                            self.assertIn("99999", path.read_text())
                    finally:
                        path.unlink()

    def test_first_install_refuses_to_replace_an_installed_engine(self):
        record = self.home / ".config/omastrix/engine.json"
        record.parent.mkdir(parents=True)
        record.write_text('{"commit": "newer-build", "version": "build 12297"}')
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_build()
        self.assertIn("already installed", result.stderr.lower())
        self.assertEqual(json.loads(record.read_text())["commit"], "newer-build")


    def test_untrusted_pin_is_refused_before_external_tools(self):
        for field, value in (("commit", "--help"), ("commit", "main"),
                             ("repo", "ext::sh -c touch /not-executed"),
                             ("repo", "https://example.invalid/fork.git")):
            with self.subTest(field=field, value=value):
                (self.repo / "engine-pin.json").write_text(json.dumps({**PIN, field: value}))
                result = self.run_installer()
                self.assertNotEqual(result.returncode, 0)
                self.assert_no_build()
                self.assertIn("pin", result.stderr.lower())


    def test_python_worker_can_install_without_relocking_its_engine_lock(self):
        for name in ("omastrix", "library.py", "webui.py", "dependencies.py"):
            shutil.copy2(ROOT / "bin" / name, self.repo / "bin" / name)
        self.control.write_text(json.dumps(self.settings))
        selected = "b" * 40
        self.settings["actual_commit"] = selected
        self.control.write_text(json.dumps(self.settings))
        for verb, args in (("engine-install-run", [selected]), ("engine-update-run", [selected])):
            with self.subTest(verb=verb):
                result = subprocess.run(
                    [sys.executable, str(self.repo / "bin/omastrix"), verb, *args],
                    capture_output=True, text=True, timeout=10,
                    env={**os.environ, "HOME": str(self.home), "COMMAND_LOG": str(self.log),
                         "CONTROL": str(self.control), **self.extra_env,
                         "PATH": str(self.tools) + os.pathsep + os.environ["PATH"]},
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                state = json.loads((self.home / ".local/state/omastrix/engine-update.json").read_text())
                self.assertEqual(state["pid"], 0)
                self.assertEqual(state["error"], "")
                record = json.loads((self.home / ".config/omastrix/engine.json").read_text())
                self.assertEqual(record["commit"], selected)
                self.assertIn("INSTALL_OK", result.stdout)

    def test_python_engine_operation_blocks_standalone_installer(self):
        import fcntl
        lock = self.home / ".local/state/omastrix/engine.lock"
        lock.parent.mkdir(parents=True)
        with lock.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_installer()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assert_no_build()
        self.assertIn("already", result.stderr.lower())

    def test_concurrent_install_is_refused(self):
        import fcntl
        lock = self.home / ".local/share/omastrix/.engine-install.lock"
        lock.parent.mkdir(parents=True)
        with lock.open("w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_build()
        self.assertIn("already", result.stderr.lower())


    def test_inherited_lock_environment_cannot_bypass_coordination(self):
        for descriptor in ("", "-1", "0", "999999", "not-an-fd"):
            with self.subTest(descriptor=descriptor):
                self.extra_env["OMASTRIX_ENGINE_LOCK_FD"] = descriptor
                result = self.run_installer()
                self.assertNotEqual(result.returncode, 0)
                self.assert_no_build()
                self.assertIn("inherited engine lock", result.stderr.lower())

    def test_unrelated_inherited_descriptor_is_not_an_engine_lock(self):
        lock = self.home / ".local/state/omastrix/engine.lock"
        lock.parent.mkdir(parents=True)
        lock.touch()
        with (self.home / "unrelated.lock").open("a") as handle:
            self.pass_fds = (handle.fileno(),)
            self.extra_env["OMASTRIX_ENGINE_LOCK_FD"] = str(handle.fileno())
            result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_build()
        self.assertIn("does not match engine.lock", result.stderr)

    def test_engine_lock_symlink_is_rejected_without_touching_target(self):
        lock = self.home / ".local/state/omastrix/engine.lock"
        lock.parent.mkdir(parents=True)
        target = self.home / "unrelated-lock"
        target.write_text("untouched")
        lock.symlink_to(target)
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_build()
        self.assertEqual(target.read_text(), "untouched")

    def test_missing_build_dependency_stops_before_clone(self):
        (self.tools / "glslc").unlink()
        for name in ("dirname", "mkdir", "flock", "cat", "chmod", "head"):
            target = shutil.which(name)
            assert target is not None, "Test prerequisite missing: " + name
            (self.tools / name).symlink_to(target)
        self.path = str(self.tools)
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_build()
        self.assertIn("glslc", result.stderr)
        self.assertIn("omarchy pkg", result.stderr)


    def test_cpu_only_build_is_not_published_as_success(self):
        self.settings["devices"] = "Available devices:\n  CPU: generic CPU (32768 MiB, 30000 MiB free)"
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("INSTALL_OK", result.stdout)
        self.assertFalse((self.home / ".config/omastrix/engine.json").exists())
        self.assertFalse((self.home / ".local/share/omastrix/bin/llama-server").exists())
        self.assertIn("radv", result.stderr.lower())


    def test_update_builds_in_isolation_and_preserves_legacy_tree(self):
        source = self.home / ".local/share/omastrix/src/strix-llama.cpp"
        (source / ".git").mkdir(parents=True)
        old_binary = source / "build/bin/llama-server"
        old_binary.parent.mkdir(parents=True)
        old_binary.write_text("old binary must not be rebuilt in place")
        result = self.run_installer(PIN["commit"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(old_binary.read_text(), "old binary must not be rebuilt in place")
        self.assertFalse(any(str(source) in row for row in self.commands()))
        wrapper = self.home / ".local/share/omastrix/bin/llama-server"
        self.assertNotIn('src/strix-llama.cpp/build', wrapper.read_text())
        self.assertIn("INSTALL_OK", result.stdout)


    def test_checkout_must_resolve_to_exact_requested_commit(self):
        self.settings["actual_commit"] = "f" * 40
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(row[0] == "cmake" for row in self.commands()))
        self.assertIn("commit", result.stderr.lower())


    def test_service_start_during_build_aborts_publication(self):
        self.settings["start_during_build"] = True
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("INSTALL_OK", result.stdout)
        self.assertFalse((self.home / ".local/share/omastrix/bin/llama-server").exists())
        self.assertFalse((self.home / ".config/omastrix/engine.json").exists())
        self.assertIn("stop", result.stderr.lower())


    def test_failed_version_probe_preserves_existing_wrapper(self):
        self.settings["version_code"] = 1
        wrapper = self.home / ".local/share/omastrix/bin/llama-server"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text("old wrapper")
        result = self.run_installer(PIN["commit"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(wrapper.read_text(), "old wrapper")
        self.assertFalse((self.home / ".config/omastrix/engine.json").exists())
        self.assertNotIn("INSTALL_OK", result.stdout)


    def test_wrapper_publication_does_not_follow_symlinks(self):
        target = self.home / "unrelated-file"
        target.write_text("do not clobber")
        wrapper = self.home / ".local/share/omastrix/bin/llama-server"
        wrapper.parent.mkdir(parents=True)
        wrapper.symlink_to(target)
        result = self.run_installer(PIN["commit"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_text(), "do not clobber")
        self.assertFalse(wrapper.is_symlink())


    def test_custom_radv_icd_path_is_used_and_shell_quoted(self):
        icd = self.home / "radeon's custom icd.json"
        icd.write_text(json.dumps({"ICD": {"library_path": "libvulkan_radeon.so"}}))
        self.extra_env = {"OMASTRIX_RADV_ICD": str(icd)}
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        env_file = self.home / ".config/omastrix/llama.env"
        probe = subprocess.run(["/bin/sh", "-c", '. "$1"; printf "%s" "$VK_DRIVER_FILES"', "sh", str(env_file)],
                               capture_output=True, text=True, timeout=5)
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(probe.stdout, str(icd))


    def test_non_strix_or_tiny_radv_heap_is_refused(self):
        for devices in ("Vulkan0: AMD Radeon RX 7900 (RADV NAVI31) (24000 MiB, 20000 MiB free)",
                        "Vulkan0: AMD Radeon 8060S (RADV STRIX_HALO) (1 MiB, 1 MiB free)"):
            with self.subTest(devices=devices):
                self.settings["devices"] = devices
                result = self.run_installer()
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("INSTALL_OK", result.stdout)
                self.assertFalse((self.home / ".config/omastrix/engine.json").exists())


    def test_fresh_install_creates_an_empty_router_preset(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        preset = self.home / ".config/omastrix/models.ini"
        self.assertTrue(preset.is_file())
        text = preset.read_text()
        self.assertIn("version = 1", text)
        self.assertNotIn("model =", text)
        self.assertNotIn("load-on-startup", text)
        commands = self.commands()
        self.assertFalse(any(row[0] == "systemctl" and any(arg in row for arg in ("start", "restart", "enable")) for row in commands))


    def test_config_publication_does_not_follow_symlinks(self):
        originals = []
        for relative in (".config/omastrix/llama.env", ".config/omastrix/engine.json",
                         ".config/systemd/user/omastrix-llama.service"):
            path = self.home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            target = self.home / (path.name + ".unrelated")
            target.write_text("do not clobber")
            path.symlink_to(target)
            originals.append((path, target))
        result = self.run_installer(PIN["commit"])
        self.assertEqual(result.returncode, 0, result.stderr)
        for path, target in originals:
            with self.subTest(path=path):
                self.assertEqual(target.read_text(), "do not clobber")
                self.assertFalse(path.is_symlink())


    def test_invalid_update_arguments_are_refused_before_build(self):
        for arguments in (("",), ("main",), ("--help",), ("A" * 40,), (PIN["commit"], "extra"),
                          ("--first-install",), ("--first-install", ""),
                          ("--first-install", "main"), ("--first-install", "b12345"),
                          ("--first-install", "A" * 40), ("--first-install", "a" * 39),
                          ("--first-install", PIN["commit"], "extra")):
            with self.subTest(arguments=arguments):
                result = self.run_installer(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assert_no_build()


    def test_failed_daemon_reload_preserves_existing_engine(self):
        self.settings["reload_code"] = 1
        wrapper = self.home / ".local/share/omastrix/bin/llama-server"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text("old wrapper")
        record = self.home / ".config/omastrix/engine.json"
        record.parent.mkdir(parents=True)
        record.write_text('{"version": "old"}')
        result = self.run_installer(PIN["commit"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(wrapper.read_text(), "old wrapper")
        self.assertEqual(record.read_text(), '{"version": "old"}')
        self.assertNotIn("INSTALL_OK", result.stdout)


    def publication_paths(self):
        return [self.home / relative for relative in (
            ".local/share/omastrix/bin/llama-server",
            ".local/share/omastrix/bin/llama-cli",
            ".local/share/omastrix/bin/llama-bench",
            ".config/omastrix/llama.env",
            ".config/systemd/user/omastrix-llama.service",
            ".config/omastrix/models.ini",
            ".config/omastrix/engine.json",
        )]

    def seed_installation(self):
        originals = {}
        for index, path in enumerate(self.publication_paths()):
            path.parent.mkdir(parents=True, exist_ok=True)
            data = b"previous installation\x00\xff\n" + path.name.encode()
            mode = 0o700 + index
            path.write_bytes(data)
            path.chmod(mode)
            originals[path] = (data, mode)
        source = self.home / ".local/share/omastrix/src/strix-llama.cpp"
        source.mkdir(parents=True)
        (source / "old-build").write_bytes(b"keep the existing build")
        return originals

    def assert_installation_restored(self, originals):
        for path, (data, mode) in originals.items():
            self.assertEqual(path.read_bytes(), data, str(path))
            self.assertEqual(path.stat().st_mode & 0o7777, mode, str(path))
        source = self.home / ".local/share/omastrix/src"
        self.assertEqual(sorted(p.name for p in source.iterdir()), ["strix-llama.cpp"])
        self.assertEqual((source / "strix-llama.cpp/old-build").read_bytes(), b"keep the existing build")
        self.assertEqual(json.loads((self.repo / "engine-pin.json").read_text()), PIN)
        self.assertEqual(list(self.home.rglob(".omastrix-publish-*")), [])

    def inject_publication_failure(self, destination):
        # Fail an actual rename once, after staging/preflight. Interpose on both
        # shell mv and Python os.replace so no production-only test hook is needed.
        self.settings["fail_destination"] = str(destination)
        (self.home / "publication-failed").unlink(missing_ok=True)
        body = f'''#!{sys.executable}
import json, os, sys
from pathlib import Path
settings = json.loads(Path(os.environ["CONTROL"]).read_text())
real_replace = os.replace
marker = Path.home() / "publication-failed"
def replacement(source, target, *args, **kwargs):
    with open(os.environ["COMMAND_LOG"], "a") as out:
        out.write(json.dumps(["publication-replace", str(target)]) + "\\n")
    if str(target) == settings.get("fail_destination") and not marker.exists():
        marker.touch()
        with open(os.environ["COMMAND_LOG"], "a") as out:
            out.write(json.dumps(["injected-publication-failure", str(target)]) + "\\n")
            if Path(target).name == "llama-cli":
                server = Path.home() / ".local/share/omastrix/bin/llama-server"
                out.write(json.dumps(["server-at-failure", server.read_bytes().hex()]) + "\\n")
        raise OSError("injected publication failure")
    return real_replace(source, target, *args, **kwargs)
if Path(sys.argv[0]).name == "mv":
    try:
        replacement(sys.argv[-2], sys.argv[-1])
    except OSError as exc:
        sys.exit(str(exc))
else:
    os.replace = replacement
    if sys.argv[1] == "-":
        code = sys.stdin.read()
        sys.argv = sys.argv[1:]
    elif sys.argv[1] == "-c":
        code = sys.argv[2]
        sys.argv = ["-c"] + sys.argv[3:]
    else:
        os.execv({sys.executable!r}, [{sys.executable!r}] + sys.argv[1:])
    exec(compile(code, "<installer>", "exec"), {{"__name__": "__main__"}})
'''
        for name in ("mv", "python3"):
            path = self.tools / name
            path.write_text(body)
            path.chmod(0o755)

    def test_mid_publication_failure_restores_existing_files_and_modes(self):
        originals = self.seed_installation()
        for target in self.publication_paths():
            if target.name == "models.ini":
                continue  # An existing user preset must not be replaced.
            with self.subTest(target=target):
                self.inject_publication_failure(target)
                self.log.unlink(missing_ok=True)
                result = self.run_installer(PIN["commit"])
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(["injected-publication-failure", str(target)], self.commands())
                self.assertNotIn("INSTALL_OK", result.stdout)
                if target.name == "llama-cli":
                    server_bytes = next(row[1] for row in self.commands() if row[0] == "server-at-failure")
                    self.assertNotEqual(bytes.fromhex(server_bytes), originals[self.publication_paths()[0]][0])
                self.assert_installation_restored(originals)

    def test_failed_first_publication_removes_all_promoted_files(self):
        for target in self.publication_paths():
            with self.subTest(target=target):
                self.inject_publication_failure(target)
                self.log.unlink(missing_ok=True)
                result = self.run_installer()
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(["injected-publication-failure", str(target)], self.commands())
                self.assertNotIn("INSTALL_OK", result.stdout)
                for path in self.publication_paths():
                    self.assertFalse(path.exists() or path.is_symlink(), str(path))
                self.assertEqual(list((self.home / ".local/share/omastrix/src").iterdir()), [])
                self.assertEqual(list(self.home.rglob(".omastrix-publish-*")), [])

    def test_first_install_reload_failure_removes_promoted_files(self):
        self.settings["reload_code"] = 1
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("INSTALL_OK", result.stdout)
        for path in self.publication_paths():
            self.assertFalse(path.exists() or path.is_symlink(), str(path))
        self.assertEqual(list((self.home / ".local/share/omastrix/src").iterdir()), [])
        self.assertEqual(list(self.home.rglob(".omastrix-publish-*")), [])

    def test_publication_rollback_restores_final_symlinks_without_touching_targets(self):
        originals = self.seed_installation()
        links = {}
        for path, (data, mode) in originals.items():
            target = self.home / (path.name + ".unrelated")
            target.write_bytes(data)
            target.chmod(mode)
            path.unlink()
            path.symlink_to(target)
            links[path] = target
        self.inject_publication_failure(self.home / ".config/omastrix/engine.json")
        result = self.run_installer(PIN["commit"])
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(["injected-publication-failure", str(self.home / ".config/omastrix/engine.json")], self.commands())
        self.assert_installation_restored(originals)
        for path, target in links.items():
            self.assertTrue(path.is_symlink(), str(path))
            self.assertEqual(os.readlink(path), str(target))
            self.assertEqual(target.read_bytes(), originals[path][0])

    def test_successful_update_promotes_entire_installation_and_keeps_user_preset(self):
        originals = self.seed_installation()
        result = self.run_installer(PIN["commit"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("INSTALL_OK", result.stdout)
        for path, (data, mode) in originals.items():
            if path.name == "models.ini":
                self.assertEqual(path.read_bytes(), data)
                self.assertEqual(path.stat().st_mode & 0o7777, mode)
            else:
                self.assertNotEqual(path.read_bytes(), data)
        record = json.loads((self.home / ".config/omastrix/engine.json").read_text())
        self.assertEqual(record["commit"], PIN["commit"])
        self.assertEqual(record["version"], "b12297 (6994643)")
        self.assertTrue(Path(record["bin"]).is_file())
        source = self.home / ".local/share/omastrix/src"
        self.assertEqual(len(list(source.iterdir())), 2)
        self.assertEqual((source / "strix-llama.cpp/old-build").read_bytes(), b"keep the existing build")
        self.assertEqual(list(self.home.rglob(".omastrix-publish-*")), [])
        for tool in ("llama-server", "llama-cli", "llama-bench"):
            wrapper = self.home / ".local/share/omastrix/bin" / tool
            self.assertEqual(wrapper.stat().st_mode & 0o7777, 0o755)
            probe = subprocess.run([str(wrapper), "--version"], capture_output=True, text=True,
                                   env={**os.environ, "HOME": str(self.home), "CONTROL": str(self.control)}, timeout=5)
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertEqual(probe.stdout.strip(), self.settings["version"])

    def test_failed_reload_restores_unit_and_entire_previous_installation(self):
        originals = self.seed_installation()
        self.settings["reload_code"] = 1
        result = self.run_installer(PIN["commit"])
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("INSTALL_OK", result.stdout)
        self.assert_installation_restored(originals)

    def test_all_directory_publication_targets_are_preflighted(self):
        originals = self.seed_installation()
        for target in self.publication_paths():
            with self.subTest(target=target):
                data, mode = originals[target]
                target.unlink()
                target.mkdir()
                self.log.unlink(missing_ok=True)
                result = self.run_installer(PIN["commit"])
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertNotIn("INSTALL_OK", result.stdout)
                self.assert_no_build()
                self.assertEqual(list(target.iterdir()), [])
                target.rmdir()
                target.write_bytes(data)
                target.chmod(mode)
                self.assert_installation_restored(originals)

    def test_directory_wrapper_target_cannot_produce_success(self):
        wrapper = self.home / ".local/share/omastrix/bin/llama-server"
        wrapper.mkdir(parents=True)
        result = self.run_installer(PIN["commit"])
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("INSTALL_OK", result.stdout)
        self.assertFalse((self.home / ".config/omastrix/engine.json").exists())
        self.assertEqual(list(wrapper.iterdir()), [])


    def test_build_parallelism_is_bounded_and_targets_are_explicit(self):
        self.extra_env["CMAKE_BUILD_PARALLEL_LEVEL"] = "3"
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        build = next(row for row in self.commands() if row[0] == "cmake" and "--build" in row)
        self.assertIn("--parallel", build)
        self.assertEqual(build[build.index("--parallel") + 1], "3")
        self.assertNotIn("-j", build)
        self.assertEqual(build[build.index("--target") + 1:], ["llama-server", "llama-cli", "llama-bench"])


    def test_first_install_refuses_a_broken_existing_wrapper(self):
        wrapper = self.home / ".local/share/omastrix/bin/llama-server"
        wrapper.parent.mkdir(parents=True)
        wrapper.symlink_to(self.home / "missing-engine")
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_build()
        self.assertTrue(wrapper.is_symlink())


if __name__ == "__main__":
    unittest.main()
