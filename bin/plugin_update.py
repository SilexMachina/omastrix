"""Manual native-plugin updates. Snapshot reads are strictly offline."""
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from datetime import datetime, timezone


def state_dir(create=False):
    path = Path.home()
    for part in (".local", "state", "omastrix"):
        path = path / part
        if create:
            try:
                path.mkdir(mode=0o700)
            except FileExistsError:
                pass
        if path.is_symlink():
            raise ValueError("Unsafe plugin state directory")
        if path.exists():
            info = path.stat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise ValueError("Unsafe plugin state directory")
    return path


def safe_open(path, flags):
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
        os.close(fd)
        raise ValueError("Unsafe plugin state file")
    return fd


def read_state():
    try:
        with os.fdopen(safe_open(state_dir() / "plugin-update.json", os.O_RDONLY)) as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}


def save_state(data):
    directory = state_dir(create=True)
    target = directory / "plugin-update.json"
    if target.exists() or target.is_symlink():
        os.close(safe_open(target, os.O_RDONLY))
    fd, name = tempfile.mkstemp(prefix=".plugin-update-", dir=directory)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream)
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def acquire_lock():
    fd = safe_open(state_dir(create=True) / "plugin.lock", os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise ValueError("Plugin updater is already running")
    return fd


def busy():
    try:
        fd = safe_open(state_dir() / "plugin.lock", os.O_RDONLY)
    except FileNotFoundError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True
    finally:
        os.close(fd)


_workers = []  # Retain detached children; reap finished children on later launches.


def worker_lock():
    inherited = os.environ.pop("OMASTRIX_PLUGIN_LOCK_FD", "")
    if not inherited:
        return acquire_lock()
    fd = int(inherited)
    actual = os.fstat(fd)
    path = state_dir() / "plugin.lock"
    check_fd = safe_open(path, os.O_RDONLY)
    try:
        expected = os.fstat(check_fd)
        if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
            raise ValueError("Invalid inherited plugin lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(check_fd)
    os.set_inheritable(fd, False)
    return fd


def start_update():
    fd = None
    try:
        fd = acquire_lock()
        data = inspect_remote(fetch=False)
        if not data["update_available"]:
            save_state(data)
            return {"success": True, "message": "Plugin is already up to date."}
        require_clean()
        data.update(pid=os.getpid(), error="", operation="update")
        save_state(data)
        environment = {**os.environ, "OMASTRIX_PLUGIN_LOCK_FD": str(fd), "PYTHONDONTWRITEBYTECODE": "1"}
        _workers[:] = [proc for proc in _workers if proc.poll() is None]
        proc = subprocess.Popen([str(root_dir() / "bin/omastrix"), "plugin-update-run"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, cwd=Path.home(), pass_fds=(fd,), env=environment)
        _workers.append(proc)
        # The worker owns completion state; never race it with a parent PID write.
        return {"success": True, "message": "Updating OmaStrix in the background."}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return failure(exc) if fd is not None else {"success": False, "error": str(exc)}
    finally:
        if fd is not None:
            os.close(fd)


def update_run():
    fd = None
    try:
        fd = worker_lock()
        mark_operation("update")
        data = inspect_remote()
        data.update(pid=os.getpid(), operation="update")
        save_state(data)
        if data["update_available"]:
            # Fetch can take time: revalidate installed target and local edits immediately before mutation.
            require_clean()
            environment = {key: value for key, value in os.environ.items()
                           if key in ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE",
                                      "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "OMARCHY_PATH",
                                      "XDG_CONFIG_HOME", "XDG_DATA_HOME")}
            environment.update(GIT_TERMINAL_PROMPT="0", GIT_PAGER="cat", PAGER="cat", SYSTEMD_PAGER="cat")
            native = subprocess.run(["omarchy", "plugin", "update", PLUGIN_ID, "--yes"],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, env=environment, timeout=180)
            if native.returncode:
                raise ValueError("Native plugin update failed (%s): %s" %
                    (native.returncode, (native.stderr or native.stdout)[-2000:].strip()))
            verified = inspect_remote(fetch=False)
            version = manifest((root_dir() / "manifest.json").read_text())
            if (verified["current_commit"] != verified["latest_commit"]
                    or not ancestor(data["latest_commit"], verified["current_commit"])
                    or version != verified["latest_version"]):
                raise ValueError("Native plugin update did not install the fetched HEAD/version")
            data = verified
        data.update(pid=0, error="")
        save_state(data)
        return {"success": True, "message": "OmaStrix plugin update complete."}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return failure(exc) if fd is not None else {"success": False, "error": str(exc)}
    finally:
        if fd is not None:
            os.close(fd)

PLUGIN_ID = "silexmachina.omastrix"


def root_dir():
    return Path(__file__).resolve().parents[1]


def git(*args):
    out = subprocess.run(["git", "-C", str(root_dir()), *args], capture_output=True,
                         text=True, timeout=60, env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat"})
    if out.returncode:
        raise ValueError((out.stderr or out.stdout or "git failed").strip())
    return out.stdout.strip()


def manifest(text):
    data = json.loads(text)
    if (not isinstance(data, dict) or data.get("id") != PLUGIN_ID
            or not isinstance(data.get("version"), str) or not data["version"].strip()):
        raise ValueError("Invalid plugin manifest identity/version")
    return data["version"]


def managed():
    installed = Path.home() / ".config/omarchy/plugins" / PLUGIN_ID
    return (installed.resolve() == root_dir().resolve()
            and (root_dir() / ".git").is_dir()
            and Path(git("rev-parse", "--show-toplevel")).resolve() == root_dir().resolve())


def status():
    result = dict(managed=False, version="", current_commit="", latest_version="",
                  latest_commit="", update_available=False, updating=False, error="", checked_at="")
    try:
        result["version"] = manifest((root_dir() / "manifest.json").read_text())
        result["managed"] = managed()
        if result["managed"]:
            result["current_commit"] = git("rev-parse", "HEAD")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result["error"] = str(exc)
    try:
        saved = read_state()
        for key in ("latest_version", "latest_commit", "checked_at", "error"):
            value = saved.get(key)
            if isinstance(value, str) and (key != "error" or not result["error"]):
                result[key] = value
        locked = busy()
        result["updating"] = locked and saved.get("operation") == "update"
        if saved.get("pid") and not locked:
            result["error"] = "Plugin update worker exited without recording completion"
        result["update_available"] = bool(result["managed"] and not result["error"]
            and not result["updating"] and saved.get("update_available") is True
            and saved.get("current_commit") == result["current_commit"])
    except (OSError, ValueError) as exc:
        result["error"] = str(exc)
    return result


def require_clean():
    if not managed():
        raise ValueError("Plugin is not the canonical installed git checkout")
    if git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Plugin checkout has local dirty work; commit or remove it first")


def ancestor(first, second):
    out = subprocess.run(["git", "-C", str(root_dir()), "merge-base", "--is-ancestor", first, second],
                         capture_output=True, text=True, timeout=15)
    if out.returncode not in (0, 1):
        raise ValueError(out.stderr.strip() or "Cannot compare plugin history")
    return out.returncode == 0


def inspect_remote(fetch=True):
    require_clean()
    if fetch:
        git("fetch", "--quiet", "origin", "HEAD")
    current = git("rev-parse", "HEAD")
    latest = git("rev-parse", "FETCH_HEAD^{commit}")
    version = manifest(git("show", "FETCH_HEAD:manifest.json"))
    behind = ancestor(current, latest)
    if not behind and not ancestor(latest, current):
        raise ValueError("Plugin checkout has diverged from origin HEAD")
    return dict(current_commit=current, latest_commit=latest, latest_version=version,
                update_available=behind and current != latest,
                checked_at=datetime.now(timezone.utc).isoformat(), error="", pid=0)


def failure(exc):
    error = str(exc)
    try:
        saved = read_state()
        saved.update(pid=0, error=error, update_available=False)
        save_state(saved)
    except (OSError, ValueError) as state_error:
        error += "; could not persist error: " + str(state_error)
    return {"success": False, "error": error}


def mark_operation(kind):
    saved = read_state()
    saved.update(pid=os.getpid() if kind == "update" else 0, error="", operation=kind)
    save_state(saved)


def check():
    fd = None
    try:
        fd = acquire_lock()
        mark_operation("check")
        save_state(inspect_remote())
        return {"success": True, "message": "Plugin update check complete."}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # A contending request must not clobber the active job's state.
        return failure(exc) if fd is not None else {"success": False, "error": str(exc)}
    finally:
        if fd is not None:
            os.close(fd)
