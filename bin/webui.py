"""Open WebUI as an OmaStrix user program.

The copy under ~/.local/share/open-webui and ~/.local/bin/open-webui-serve is a
hand install. This module does not start it, stop it, or read its secret.
"""

import functools
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import time
import uuid

import library

UNIT = "omastrix-webui.service"
PORT = 3000
# Approved product baseline; explicit updates never reset an installed version.
INITIAL_VERSION = "0.13.0"
PYTHON_VERSION = "3.11"

# The same guard runs before service launch and inside the generated wrapper.
ACCESS_GUARD = r'''import os, sqlite3, sys
from pathlib import Path
from contextlib import closing
from urllib.parse import quote
host = os.environ.get("HOST", "127.0.0.1")
if host in ("127.0.0.1", "localhost", "::1"):
    sys.exit(0)
if os.environ.get("WEBUI_AUTH", "true").lower() != "true":
    sys.exit("Network access requires authentication.")
if os.environ.get("DATABASE_URL"):
    sys.exit("Network access requires a locally verifiable administrator account; custom DATABASE_URL is unsupported.")
path = Path(os.environ["DATA_DIR"]) / "webui.db"
if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
    sys.exit("Cannot verify the administrator account through a redirected database path.")
try:
    with closing(sqlite3.connect("file:" + quote(str(path), safe="/") + "?mode=ro", uri=True, timeout=2)) as db:
        ready = db.execute('SELECT 1 FROM "user" WHERE role = ? LIMIT 1', ("admin",)).fetchone()
    if not ready:
        raise ValueError("missing administrator")
except (sqlite3.Error, ValueError):
    sys.exit("Create an administrator account on this device before enabling network access.")
'''



def safe_path(path, allow_leaf_link=False):
    """Reject redirection in every ancestor, including HOME and its parents."""
    path = os.path.abspath(path)
    current = os.path.sep
    parts = path.split(os.path.sep)[1:]
    for index, part in enumerate(parts):
        current = os.path.join(current, part)
        leaf = index == len(parts) - 1
        if os.path.islink(current) and not (leaf and allow_leaf_link):
            raise ValueError("Open WebUI path contains a symlink: " + current)
        if not leaf and os.path.lexists(current) and not os.path.isdir(current):
            raise ValueError("Open WebUI ancestor is not a directory: " + current)
    return path


def safe_layout():
    for relative in (
        ".local/state/omastrix/webui.lock", ".local/state/omastrix/webui-install.json",
        ".local/state/omastrix/webui-update.json", ".local/state/omastrix/webui-check.json",
        ".local/state/omastrix/webui-install.log", ".local/state/omastrix/webui-update.log",
        ".local/share/omastrix/webui/venvs", ".config/omastrix/webui.env",
    ):
        safe_path(os.path.join(home(), relative))
    for path in (wrapper_path(), unit_path()):
        safe_path(path, allow_leaf_link=True)  # Atomic replacement, never dereference.


def serialized(*, wait=False, worker=False, job=None):
    """Check ancestors before library.serialized opens its lock or error state."""
    def decorate(fn):
        error_state = (lambda *args, **kwargs: job_path(job)) if job else None
        locked = library.serialized("webui", wait=wait, worker=worker, error_state=error_state)(fn)
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            try:
                safe_layout()
            except (OSError, ValueError) as exc:
                error = str(exc)
                if job:
                    try:
                        path = safe_path(os.path.join(home(), ".local/state/omastrix/webui-" + job + ".json"))
                        library.atomic_json(path, {"pid": 0, "error": error})
                    except (OSError, ValueError) as state_error:
                        error += "; could not save failure state: " + str(state_error)
                result = {"success": False, "error": error}
                if worker:
                    print(json.dumps(result))
                    return 1
                return result
            return locked(*args, **kwargs)
        return wrapped
    return decorate


def job_path(job):
    return os.path.join(state_dir(), "webui-" + job + ".json")


def home():
    return os.path.expanduser("~")


def prefix():
    return os.path.join(home(), ".local/share/omastrix/webui")


def webui_bin():
    return os.path.join(prefix(), "venv/bin/open-webui")


def env_path():
    return os.path.join(home(), ".config/omastrix/webui.env")


def wrapper_path():
    return os.path.join(home(), ".local/share/omastrix/bin/omastrix-webui")


def unit_path():
    return os.path.join(home(), ".config/systemd/user", UNIT)


def state_dir():
    path = os.path.join(home(), ".local/state/omastrix")
    os.makedirs(path, exist_ok=True)
    return path


def install_state_path():
    return os.path.join(state_dir(), "webui-install.json")


def find_uv():
    found = shutil.which("uv")
    if found:
        return found
    for path in (
        os.path.join(home(), ".local/bin/uv"),
        os.path.join(home(), ".hermes/bin/uv"),
    ):
        if os.access(path, os.X_OK):
            return path
    return ""


def systemctl(*args):
    try:
        out = subprocess.run(
            ["systemctl", "--user", *args],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    text = (out.stdout or out.stderr or "").strip()
    return out.returncode, text


def port_open():
    try:
        out = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    for line in (out.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[3].endswith(":%s" % PORT):
            return True
    return False


def version_of(path):
    py = os.path.join(os.path.dirname(path), "python")
    if not os.access(py, os.X_OK):
        return ""
    try:
        out = subprocess.run(
            [py, "-c", "import importlib.metadata as m; print(m.version('open-webui'))"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    text = (out.stdout or "").strip()
    if out.returncode != 0 or version_key(text) is None:
        return ""
    return text


def read_install_state():
    try:
        with open(install_state_path()) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    pid = data.get("pid")
    running = False
    if pid:
        try:
            os.kill(int(pid), 0)
            running = True
        except (OSError, ValueError):
            running = False
    data["running"] = running
    return data


def write_env():
    safe_path(env_path())
    os.makedirs(os.path.dirname(env_path()), exist_ok=True)
    if os.path.exists(env_path()):
        os.chmod(env_path(), 0o600)
        return
    secret = secrets.token_hex(32)
    body = "\n".join([
        "ENABLE_OLLAMA_API=false",
        "ENABLE_OPENAI_API=true",
        "OPENAI_API_BASE_URL=http://127.0.0.1:8080/v1",
        "OPENAI_API_KEY=sk-local",
        "OPENAI_API_BASE_URLS=http://127.0.0.1:8080/v1",
        "OPENAI_API_KEYS=sk-local",
        "PORT=%s" % PORT,
        "HOST=127.0.0.1",
        "WEBUI_AUTH=true",
        "ENABLE_SIGNUP=false",
        "WEBUI_SECRET_KEY=%s" % secret,
        "DATA_DIR=%s" % shlex.quote(os.path.join(prefix(), "data")),
        "",
    ])
    fd = os.open(env_path(), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(body)


def access_config():
    values = {"HOST": "127.0.0.1", "DATA_DIR": os.path.join(prefix(), "data"), "WEBUI_AUTH": "true"}
    if not os.path.exists(env_path()):
        return values
    safe_path(env_path())
    seen = set()
    with open(env_path()) as fh:
        for line in fh:
            tokens = shlex.split(line, comments=True)
            if tokens and tokens[0] == "export":
                tokens = tokens[1:]
            for token in tokens:
                key, sep, value = token.partition("=")
                if sep and key in ("HOST", "DATA_DIR", "WEBUI_AUTH", "DATABASE_URL"):
                    if key in seen or any(c in value for c in ("$", "`", "\n", "\r")):
                        raise ValueError("Ambiguous Open WebUI access configuration: " + key)
                    seen.add(key)
                    values[key] = value
    return values


def access_settings():
    config = access_config()
    local = config["HOST"] in ("127.0.0.1", "localhost", "::1")
    return {"access": "local" if local else "network", "bind_host": config["HOST"]}


def check_network_access(config):
    result = subprocess.run([sys.executable, "-c", ACCESS_GUARD],
                            env=config, capture_output=True, text=True, timeout=5, check=False)
    if result.returncode:
        raise ValueError((result.stderr or "Could not verify Open WebUI network access.").strip())


@serialized()
def set_access(mode, confirm=False):
    if mode not in ("local", "network"):
        return {"success": False, "error": "Access must be local or network."}
    require_stopped()
    if not os.path.isfile(env_path()):
        return {"success": False, "error": "Install Open WebUI first."}
    config = access_config()
    host = "127.0.0.1" if mode == "local" else "0.0.0.0"
    if mode == "network":
        check_network_access(dict(config, HOST=host))
        if not confirm:
            return {"success": False, "needs_confirm": True,
                    "error": "Listen on all network interfaces on port 3000? Restrict access to trusted devices; this connection has no TLS."}
    with open(env_path()) as fh:
        body = fh.read()
    body, count = re.subn(r"(?m)^[ \t]*(?:export[ \t]+)?HOST=.*$", "HOST=" + host, body)
    if not count:
        body = body.rstrip("\n") + "\nHOST=" + host + "\n"
    write_wrapper()
    library.atomic_text(env_path(), body, 0o600)
    return {"success": True, "access": mode}


def write_wrapper():
    os.makedirs(os.path.dirname(wrapper_path()), exist_ok=True)
    text = """#!/bin/sh
set -eu
set -a
. "${HOME}/.config/omastrix/webui.env"
set +a
export WEBUI_AUTH=true
export ENABLE_SIGNUP=false
python3 - << 'OMASTRIX_ACCESS_CHECK'
""" + ACCESS_GUARD + """OMASTRIX_ACCESS_CHECK
mkdir -p "$DATA_DIR"
exec "${HOME}/.local/share/omastrix/webui/venv/bin/open-webui" serve --host "$HOST" --port "$PORT"
"""
    library.atomic_text(wrapper_path(), text, 0o755)


def write_unit():
    os.makedirs(os.path.dirname(unit_path()), exist_ok=True)
    text = """[Unit]
Description=OmaStrix Open WebUI
After=default.target

[Service]
Type=simple
ExecStart=%h/.local/share/omastrix/bin/omastrix-webui
Restart=no
StandardOutput=append:%h/.local/state/omastrix/webui.log
StandardError=append:%h/.local/state/omastrix/webui.log

[Install]
WantedBy=default.target
"""
    library.atomic_text(unit_path(), text)
    code, error = systemctl("daemon-reload")
    if code != 0:
        raise OSError(error or "Could not reload Open WebUI service configuration")


def ensure_layout():
    write_env()
    write_wrapper()
    write_unit()


def status():
    try:
        safe_layout()
        installed = current_venv() is not None
        access = access_settings()
    except (OSError, ValueError) as exc:
        return {"installed": False, "running": False, "state": "unavailable", "version": "",
                "latest_version": "", "update_available": False, "updating": False,
                "url": "http://127.0.0.1:3000", "error": str(exc)}
    install = read_install_state()
    active, active_text = systemctl("is-active", UNIT)
    state = library.service_state(active, active_text)
    if install.get("running") and state in ("stopped", "failed"):
        state = "installing"
    elif not installed and state in ("stopped", "failed"):
        state = "not_installed"
    version = version_of(webui_bin()) if installed else ""
    return {
        **access,
        "installed": installed,
        "running": state == "running",
        "state": state,
        "version": version,
        "latest_version": read_json(check_path()).get("latest") or "",
        "update_available": update_available(installed, version),
        "updating": read_update_state().get("running") is True,
        "url": "http://127.0.0.1:3000",
        "error": install.get("error") or read_update_state().get("error") or "",
    }


@serialized()
def start():
    if not os.access(webui_bin(), os.X_OK):
        return {"success": False, "error": "Open WebUI is not installed."}
    if port_open():
        active, active_text = systemctl("is-active", UNIT)
        if active_text != "active":
            return {"success": False, "error": "Port 3000 is already in use."}
        return {"success": True, "message": "Open WebUI is already running."}
    check_network_access(access_config())
    ensure_layout()
    code, text = systemctl("start", UNIT)
    if code != 0:
        return {"success": False, "error": text or "Open WebUI did not start."}
    deadline = time.time() + 60
    while time.time() < deadline:
        if port_open():
            return {"success": True, "message": "Open WebUI is running."}
        active, active_text = systemctl("is-active", UNIT)
        if active_text == "failed":
            return {"success": False, "error": "Open WebUI failed to start. See ~/.local/state/omastrix/webui.log"}
        time.sleep(1)
    return {"success": False, "error": "Open WebUI did not open port 3000."}


def stop():
    code, text = systemctl("stop", UNIT)
    deadline = time.time() + 20
    while time.time() < deadline and port_open():
        time.sleep(0.5)
    if port_open():
        return {"success": False, "error": "Port 3000 is still in use."}
    if code != 0 and "not loaded" not in text.lower():
        return {"success": False, "error": text or "Open WebUI did not stop."}
    return {"success": True, "message": "Open WebUI is stopped."}


def current_venv():
    pointer = os.path.join(prefix(), "venv")
    if not os.path.lexists(pointer):
        return None
    managed = os.path.islink(pointer)
    if managed:
        relative = os.readlink(pointer)
        if not re.fullmatch(r"venvs/[a-f0-9]{32}", relative):
            raise ValueError("Foreign Open WebUI venv pointer; refusing to use it.")
        venv = safe_path(os.path.join(prefix(), relative))
    else:
        venv = safe_path(pointer)
    for relative in ("pyvenv.cfg", "bin", "bin/open-webui", ".omastrix.json"):
        safe_path(os.path.join(venv, relative))
    if not os.path.isfile(os.path.join(venv, "pyvenv.cfg")) or not os.access(os.path.join(venv, "bin/open-webui"), os.X_OK):
        raise ValueError("Incomplete or foreign Open WebUI venv layout.")
    metadata_path = os.path.join(venv, ".omastrix.json")
    metadata = None
    if managed or os.path.lexists(metadata_path):
        with open(metadata_path) as fh:
            metadata = json.load(fh)
        if (not isinstance(metadata, dict) or set(metadata) != {"schema", "version", "python"}
                or type(metadata["schema"]) is not int or metadata["schema"] != 1
                or metadata["python"] != PYTHON_VERSION or version_key(metadata["version"]) is None):
            raise ValueError("Malformed Open WebUI venv metadata.")
    actual = version_of(os.path.join(venv, "bin/open-webui"))
    if version_key(actual) is None or (metadata and metadata["version"] != actual):
        raise ValueError("Open WebUI venv metadata/distribution version mismatch.")
    return venv


def require_stopped():
    code, text = systemctl("is-active", UNIT)
    if library.service_state(code, text) not in ("stopped", "failed"):
        raise ValueError("Stop Open WebUI before installation or updating; service state must be known stopped.")


def promote(venv, version, job_path, update=False):
    """Rollback executables/config on publication failure, never database contents."""
    safe_layout()
    current_venv()  # Recheck foreign pointers/metadata after the long build.
    pointer = os.path.join(prefix(), "venv")
    old = os.readlink(pointer) if os.path.islink(pointer) else None
    snapshots = {}
    for path in (env_path(), wrapper_path(), unit_path(), check_path()):
        if os.path.exists(path):
            with open(path, "rb") as fh:
                snapshots[path] = (fh.read(), os.stat(path).st_mode & 0o777)
        else:
            snapshots[path] = None
    switched = False
    legacy = None
    legacy_metadata_added = False
    try:
        require_stopped()
        ensure_layout()
        if os.path.isdir(pointer) and not os.path.islink(pointer):
            # Preserve the old directory for rollback. No pip changes to its files.
            legacy = os.path.join(prefix(), "venvs", uuid.uuid4().hex)
            os.makedirs(os.path.dirname(legacy), exist_ok=True)
            metadata = os.path.join(pointer, ".omastrix.json")
            if not os.path.exists(metadata):
                library.atomic_json(metadata, {"schema": 1, "version": version_of(webui_bin()), "python": PYTHON_VERSION})
                legacy_metadata_added = True
        require_stopped()  # Immediately before migration/atomic pointer replacement.
        if legacy is not None:
            os.rename(pointer, legacy)
            if venv == pointer:
                venv = legacy
        switch_pointer(venv)
        switched = True
        if update:
            library.atomic_json(check_path(), {"latest": version})
        library.atomic_json(job_path, {"pid": 0, "error": "", "version": version})
    except BaseException as exc:
        failures = []
        if legacy is not None:
            try:
                if os.path.isdir(legacy):
                    if os.path.islink(pointer):
                        os.unlink(pointer)
                    os.rename(legacy, pointer)
                if legacy_metadata_added:
                    os.unlink(os.path.join(pointer, ".omastrix.json"))
            except OSError as rollback:
                failures.append(str(rollback))
        elif switched:
            try:
                if old is None:
                    os.unlink(pointer)
                else:
                    switch_pointer(os.path.join(prefix(), old))
            except OSError as rollback:
                failures.append(str(rollback))
        for path, snapshot in snapshots.items():
            try:
                if snapshot is None:
                    if os.path.lexists(path):
                        os.unlink(path)
                else:
                    body, mode = snapshot
                    temporary = path + ".rollback-" + uuid.uuid4().hex
                    try:
                        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
                        with os.fdopen(fd, "wb") as fh:
                            fh.write(body)
                        os.replace(temporary, path)
                    finally:
                        if os.path.lexists(temporary):
                            os.unlink(temporary)
            except OSError as rollback:
                failures.append(str(rollback))
        code, text = systemctl("daemon-reload")
        if code:
            failures.append("restored files but daemon-reload failed: " + text)
        if failures:
            raise OSError(str(exc) + "; rollback incomplete: " + "; ".join(failures)) from exc
        raise


def switch_pointer(venv):
    temporary = os.path.join(prefix(), ".venv-" + uuid.uuid4().hex)
    try:
        os.symlink(os.path.relpath(venv, prefix()), temporary)
        os.replace(temporary, os.path.join(prefix(), "venv"))
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def build_venv(uv, version, logfile):
    # Build at its permanent unique path: venv entry-point shebangs are absolute.
    venv = os.path.join(prefix(), "venvs", uuid.uuid4().hex)
    os.makedirs(os.path.dirname(venv), exist_ok=True)
    py = os.path.join(venv, "bin/python")
    steps = [
        [uv, "venv", venv, "--python", PYTHON_VERSION],
        [uv, "pip", "install", "--python", py, "open-webui==%s" % version],
        [uv, "pip", "check", "--python", py],
    ]
    try:
        with open(os.path.join(state_dir(), logfile), "ab") as log:
            for cmd in steps:
                if subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=False).returncode:
                    raise ValueError("Open WebUI build or dependency check failed. See " + logfile)
        probed = subprocess.run([py, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                                capture_output=True, text=True, timeout=15, check=False)
        if probed.returncode or (probed.stdout or "").strip() != PYTHON_VERSION:
            raise ValueError("Open WebUI build did not use Python " + PYTHON_VERSION)
        binary = safe_path(os.path.join(venv, "bin/open-webui"))
        if not os.path.isfile(binary) or not os.access(binary, os.X_OK):
            raise ValueError("Open WebUI build is missing its executable.")
        if version_of(binary) != version:
            raise ValueError("Installed Open WebUI distribution version does not match " + version)
        library.atomic_json(os.path.join(venv, ".omastrix.json"),
                            {"schema": 1, "version": version, "python": PYTHON_VERSION})
        return venv
    except BaseException:
        if os.path.isdir(venv):
            shutil.rmtree(venv)
        raise


@serialized(wait=True, worker=True, job="install")
def install():
    existing = current_venv()
    require_stopped()
    version = version_of(webui_bin()) if existing else INITIAL_VERSION
    legacy = os.path.isdir(os.path.join(prefix(), "venv")) and not os.path.islink(os.path.join(prefix(), "venv"))
    if existing and not legacy:
        promote(existing, version, install_state_path())
        print(json.dumps({"success": True, "message": "Open WebUI is already installed."}))
        return 0
    uv = find_uv()
    if not uv:
        raise ValueError("Open WebUI installation requires uv.")
    # A legacy venv cannot be relocated and reused: entry-point shebangs and
    # activation scripts contain its absolute original path. Rebuild the SAME
    # distribution version, verify dependencies, then preserve the old tree only
    # as rollback material. Never downgrade an existing legacy installation.
    venv = build_venv(uv, version, "webui-install.log")
    promote(venv, version, install_state_path())
    print(json.dumps({"success": True, "message": "Open WebUI installed."}))
    return 0


@serialized(job="install")
def start_install():
    existing = current_venv()
    pointer = os.path.join(prefix(), "venv")
    if existing:
        require_stopped()
        if os.path.islink(pointer):
            promote(existing, version_of(webui_bin()), install_state_path())
            return {"success": True, "message": "Open WebUI is already installed."}
        # A legacy directory needs a checked rebuild in the install worker.
    state = read_install_state()
    if state.get("running"):
        return {"success": True, "message": "Open WebUI install is already running."}
    if not find_uv():
        return {
            "success": False,
            "error": "Open WebUI installation requires uv.",
        }
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(state_dir(), "webui-install.log"), "ab") as log:
        proc = subprocess.Popen(
            [os.path.join(root, "bin/omastrix"), "webui-install-run"],
            start_new_session=True,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    library.atomic_json(install_state_path(), {'pid': proc.pid, 'error': ''})
    return {"success": True, "message": "Installing Open WebUI."}


def check_path():
    return os.path.join(state_dir(), "webui-check.json")


def update_state_path():
    return os.path.join(state_dir(), "webui-update.json")


def read_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def read_update_state():
    data = read_json(update_state_path())
    pid = data.get("pid")
    running = False
    if isinstance(pid, int) and pid > 0:
        try:
            os.kill(pid, 0)
            running = True
        except OSError:
            running = False
    data["running"] = running
    return data


def version_key(text):
    if not isinstance(text, str) or len(text) > 40 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", text):
        return None
    return tuple(int(part) for part in text.split("."))


def specifier_allows(spec, major, minor):
    version = (major, minor)
    for raw in (spec or "").split(","):
        part = raw.strip()
        if not part:
            continue
        if part.startswith(">="):
            need = version_key(part[2:].split("a", 1)[0])
            if need and version < need[:2]:
                return False
        elif part.startswith("<=") or part.startswith(">"):
            continue
        elif part.startswith("<"):
            need = version_key(part[1:].split("a", 1)[0])
            if need and version >= need[:2]:
                return False
    return True


def venv_python():
    return os.path.join(prefix(), "venv/bin/python")


def latest_release():
    try:
        out = subprocess.run(
            ["curl", "-fsS", "--max-time", "25", "https://pypi.org/pypi/open-webui/json"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, "Could not check for a newer Open WebUI version."
    if out.returncode != 0 or not out.stdout:
        return None, "Could not check for a newer Open WebUI version."
    try:
        info = json.loads(out.stdout).get("info") or {}
    except json.JSONDecodeError:
        return None, "Could not read the published Open WebUI version."
    version = info.get("version") or ""
    if version_key(version) is None:
        return None, "The published Open WebUI version is not a stable release."
    py = venv_python()
    if os.access(py, os.X_OK):
        probed = subprocess.run(
            [py, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        parts = (probed.stdout or "").strip().split(".")
        if len(parts) == 2 and all(part.isdigit() for part in parts):
            if not specifier_allows(info.get("requires_python") or "", int(parts[0]), int(parts[1])):
                return None, "Open WebUI %s needs a different Python than the one installed." % version
    return version, ""


def update_available(installed, current):
    if not installed:
        return False
    latest = version_key(read_json(check_path()).get("latest") or "")
    have = version_key(current)
    if not latest or not have:
        return False
    return latest > have and not read_update_state().get("running")


def check():
    if not os.access(webui_bin(), os.X_OK):
        return {"success": False, "error": "Open WebUI is not installed."}
    latest, err = latest_release()
    if err:
        return {"success": False, "error": err}
    current = version_of(webui_bin())
    os.makedirs(state_dir(), exist_ok=True)
    library.atomic_json(check_path(), {'latest': latest})
    latest_key = version_key(latest)
    current_key = version_key(current)
    newer = bool(latest_key and current_key and latest_key > current_key)
    if newer:
        message = "A newer Open WebUI is published: %s. You have %s." % (latest, current)
    else:
        message = "Open WebUI is the newest published version, %s." % current
    return {
        "success": True,
        "latest_version": latest,
        "version": current,
        "update_available": newer,
        "message": message,
    }


@serialized()
def start_update():
    if status().get("state") not in ("stopped", "failed"):
        return {
            "success": False,
            "error": "Stop Open WebUI before updating.",
        }
    state = read_update_state()
    if state.get("running"):
        return {"success": True, "message": "Open WebUI is already updating."}
    latest, err = latest_release()
    if not latest or err:
        return {"success": False, "error": err or "Could not check for a newer Open WebUI version."}
    current = version_of(webui_bin())
    latest_key = version_key(latest)
    current_key = version_key(current)
    if current_key and latest_key and latest_key <= current_key:
        return {"success": True, "message": "Open WebUI is already the newest published version, %s." % current}
    if not find_uv():
        return {"success": False, "error": "Open WebUI update needs uv, and uv is not installed."}
    os.makedirs(state_dir(), exist_ok=True)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(state_dir(), "webui-update.log"), "ab") as log:
        proc = subprocess.Popen(
            [os.path.join(root, "bin/omastrix"), "webui-update-run", latest],
            start_new_session=True,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    library.atomic_json(update_state_path(), {'pid': proc.pid, 'error': '', 'version': latest})
    return {"success": True, "message": "Updating Open WebUI to %s." % latest}


@serialized(wait=True, worker=True, job="update")
def update_run(version):
    if version_key(version) is None:
        raise ValueError("Open WebUI update needs a stable exact version")
    code, active = systemctl("is-active", UNIT)
    if library.service_state(code, active) not in ("stopped", "failed"):
        library.atomic_json(update_state_path(), {'pid': 0, 'error': 'Stop Open WebUI before updating.'})
        return 1
    current_venv()
    uv = find_uv()
    py = venv_python()
    if not uv or not os.access(py, os.X_OK):
        library.atomic_json(update_state_path(), {'pid': 0, 'error': 'Open WebUI update could not find its Python.'})
        return 1
    venv = build_venv(uv, version, "webui-update.log")
    promote(venv, version, update_state_path(), update=True)
    return 0
