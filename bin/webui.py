"""Open WebUI as an OmaStrix user program.

The copy under ~/.local/share/open-webui and ~/.local/bin/open-webui-serve is a
hand install. This module does not start it, stop it, or read its secret.
"""

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time

UNIT = "omastrix-webui.service"
PORT = 3000


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
    if not text or len(text) > 20 or " " in text:
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
    os.makedirs(os.path.dirname(env_path()), exist_ok=True)
    if os.path.exists(env_path()):
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
        "HOST=0.0.0.0",
        "WEBUI_AUTH=true",
        "ENABLE_SIGNUP=false",
        "WEBUI_SECRET_KEY=%s" % secret,
        "DATA_DIR=%s" % os.path.join(prefix(), "data"),
        "",
    ])
    fd = os.open(env_path(), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(body)


def write_wrapper():
    os.makedirs(os.path.dirname(wrapper_path()), exist_ok=True)
    text = """#!/bin/sh
set -eu
set -a
. "${HOME}/.config/omastrix/webui.env"
set +a
mkdir -p "$DATA_DIR"
exec "${HOME}/.local/share/omastrix/webui/venv/bin/open-webui" serve --host "$HOST" --port "$PORT"
"""
    with open(wrapper_path(), "w") as fh:
        fh.write(text)
    os.chmod(wrapper_path(), 0o755)


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
    with open(unit_path(), "w") as fh:
        fh.write(text)
    systemctl("daemon-reload")


def ensure_layout():
    write_env()
    write_wrapper()
    write_unit()


def status():
    installed = os.access(webui_bin(), os.X_OK)
    install = read_install_state()
    active, active_text = systemctl("is-active", UNIT)
    running = active_text == "active" or (installed and port_open() and active_text == "active")
    if active_text == "active":
        state = "running"
    elif install.get("running"):
        state = "installing"
    elif installed:
        state = "stopped"
    else:
        state = "not_installed"
    version = version_of(webui_bin()) if installed else ""
    return {
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


def start():
    if not os.access(webui_bin(), os.X_OK):
        return {"success": False, "error": "Open WebUI is not installed."}
    if port_open():
        active, active_text = systemctl("is-active", UNIT)
        if active_text != "active":
            return {"success": False, "error": "Port 3000 is already in use."}
        return {"success": True, "message": "Open WebUI is already running."}
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


def install():
    if os.access(webui_bin(), os.X_OK):
        ensure_layout()
        print(json.dumps({"success": True, "message": "Open WebUI is already installed."}))
        return 0
    uv = find_uv()
    if not uv:
        print(json.dumps({
            "success": False,
            "error": "Open WebUI needs Python 3.11 or 3.12. This system Python is too new, and uv is not installed.",
        }))
        return 1
    os.makedirs(prefix(), exist_ok=True)
    os.makedirs(state_dir(), exist_ok=True)
    log = open(os.path.join(state_dir(), "webui-install.log"), "ab")
    venv = os.path.join(prefix(), "venv")
    steps = [
        [uv, "venv", venv, "--python", "3.11"],
        [uv, "pip", "install", "--python", os.path.join(venv, "bin/python"), "open-webui"],
    ]
    for cmd in steps:
        proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=False)
        if proc.returncode != 0:
            with open(install_state_path(), "w") as fh:
                json.dump({"pid": 0, "error": "Install failed. See ~/.local/state/omastrix/webui-install.log"}, fh)
            print(json.dumps({"success": False, "error": "Open WebUI install failed."}))
            return 1
    ensure_layout()
    with open(install_state_path(), "w") as fh:
        json.dump({"pid": 0, "error": ""}, fh)
    print(json.dumps({"success": True, "message": "Open WebUI is installed. It is not started."}))
    return 0


def start_install():
    if os.access(webui_bin(), os.X_OK):
        ensure_layout()
        return {"success": True, "message": "Open WebUI is already installed."}
    state = read_install_state()
    if state.get("running"):
        return {"success": True, "message": "Open WebUI install is already running."}
    if not find_uv():
        return {
            "success": False,
            "error": "Open WebUI needs Python 3.11 or 3.12. This system Python is too new, and uv is not installed.",
        }
    log = open(os.path.join(state_dir(), "webui-install.log"), "ab")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.Popen(
        [os.path.join(root, "bin/omastrix"), "webui-install-run"],
        start_new_session=True,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    with open(install_state_path(), "w") as fh:
        json.dump({"pid": proc.pid, "error": ""}, fh)
    return {"success": True, "message": "Installing Open WebUI into the user profile. It will not start."}


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
    if not text or not re.fullmatch(r"\d+(?:\.\d+)+", text):
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
    with open(check_path(), "w") as fh:
        json.dump({"latest": latest}, fh)
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


def start_update():
    if status().get("running"):
        return {
            "success": False,
            "error": "Stop Open WebUI before updating. The program that is running would be replaced.",
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
    log = open(os.path.join(state_dir(), "webui-update.log"), "ab")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.Popen(
        [os.path.join(root, "bin/omastrix"), "webui-update-run", latest],
        start_new_session=True,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    with open(update_state_path(), "w") as fh:
        json.dump({"pid": proc.pid, "error": "", "version": latest}, fh)
    return {"success": True, "message": "Updating Open WebUI to %s. It will not start." % latest}


def update_run(version):
    if version_key(version) is None:
        print("Open WebUI update needs a version", file=sys.stderr)
        return 2
    uv = find_uv()
    py = venv_python()
    if not uv or not os.access(py, os.X_OK):
        with open(update_state_path(), "w") as fh:
            json.dump({"pid": 0, "error": "Open WebUI update could not find its Python."}, fh)
        return 1
    code = subprocess.call([uv, "pip", "install", "--python", py, "open-webui==%s" % version])
    if code != 0:
        with open(update_state_path(), "w") as fh:
            json.dump({"pid": 0, "error": "Update failed. See ~/.local/state/omastrix/webui-update.log"}, fh)
        return 1
    ensure_layout()
    with open(update_state_path(), "w") as fh:
        json.dump({"pid": 0, "error": "", "version": version}, fh)
    with open(check_path(), "w") as fh:
        json.dump({"latest": version}, fh)
    return 0
