"""Starter library. Reads ~/models. Does not download or load unless a verb asks."""

import configparser
import hashlib
import fcntl
import functools
import json
import os
import re
import signal
import secrets
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

RESERVE_GIB = 14
HOST = "127.0.0.1"
PORT = 8080


def service_state(code, text):
    """Interpret is-active without treating a failed probe as stopped."""
    if code not in (0, 3):
        return "unavailable"
    return {"active": "running", "inactive": "stopped", "failed": "failed",
            "activating": "starting", "deactivating": "stopping",
            "reloading": "starting"}.get(text, "unavailable")


def root_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def catalog_path():
    return os.path.join(root_dir(), "catalog.json")


def models_root():
    return os.path.join(os.path.expanduser("~"), "models")


def preset_path():
    return os.path.join(os.path.expanduser("~"), ".config/omastrix/models.ini")


def state_dir():
    path = os.path.join(os.path.expanduser("~"), ".local/state/omastrix/downloads")
    os.makedirs(path, exist_ok=True)
    return path


def ledger_path():
    return os.path.join(os.path.expanduser("~"), ".local/state/omastrix/ledger.json")


def load_catalog():
    with open(catalog_path()) as fh:
        data = json.load(fh)
    return data["models"], float(data.get("reserve_gib", RESERVE_GIB))


def added_path():
    return os.path.join(os.path.expanduser("~"), ".config/omastrix/added.json")


def load_added():
    try:
        with open(added_path()) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    models = data.get("models") if isinstance(data, dict) else None
    return models if isinstance(models, list) else []


def atomic_text(path, text, mode=0o644, *, reject_symlink=False):
    """Publish via a pinned directory, never following symlink ancestors."""
    parent, name = os.path.split(os.path.abspath(path))
    directory = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY)
    temporary = None
    try:
        for part in parent.split(os.sep):
            if not part:
                continue
            try:
                os.mkdir(part, dir_fd=directory)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        try:
            existing = os.stat(name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if not (stat.S_ISREG(existing.st_mode) or
                    (stat.S_ISLNK(existing.st_mode) and not reject_symlink)):
                raise ValueError("refusing to publish over a symlink or non-file")
        candidate = ".omastrix-" + secrets.token_hex(16)
        fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        temporary = candidate
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
            os.fchmod(fh.fileno(), mode)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        temporary = None
    finally:
        try:
            if temporary is not None:
                os.unlink(temporary, dir_fd=directory)
        finally:
            os.close(directory)


def atomic_json(path, data):
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=parent, delete=False) as fh:
            tmp = fh.name
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def serialized(name, *, wait=False, worker=False, error_state=None):
    """Serialize profile mutations; workers wait for their launcher to publish PID."""
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            path = os.path.join(os.path.expanduser("~"), ".local/state/omastrix", name + ".lock")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
                except BlockingIOError:
                    result = {"success": False, "error": "Another %s operation is running." % name}
                    if worker:
                        print(json.dumps(result))
                        return 1
                    return result
                try:
                    return fn(*args, **kwargs)
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    result = {"success": False, "error": str(exc)}
                    if error_state is not None:
                        try:
                            atomic_json(error_state(*args, **kwargs), {"pid": 0, "error": str(exc)})
                        except (OSError, ValueError) as state_error:
                            result["error"] += "; could not save failure state: " + str(state_error)
                    if worker:
                        print(json.dumps(result))
                        return 1
                    return result
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
        return wrapped
    return decorate


def save_added(models):
    atomic_json(added_path(), {"models": models})


def all_models():
    models, reserve = load_catalog()
    return models + load_added(), reserve


def find_model(model_id):
    models, reserve = all_models()
    for row in models:
        if row["id"] == model_id:
            return row, reserve
    return None, reserve


def dest_for(rel):
    if not isinstance(rel, str) or os.path.isabs(rel) or any(
        part in ("", ".", "..") for part in rel.split(os.sep)
    ):
        raise ValueError("model path must be relative to ~/models")
    if os.path.islink(models_root()):
        raise ValueError("~/models must not be a symlink")
    root = os.path.realpath(models_root())
    dest = root
    for part in rel.split(os.sep):
        dest = os.path.join(dest, part)
        if os.path.islink(dest):
            raise ValueError("model path contains a symlink")
    return dest


def file_bytes(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def size_label(nbytes):
    gib = nbytes / 1024**3
    if gib >= 10:
        return round(gib, 1)
    return round(gib, 2)


def pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    return True


def download_path(model_id, suffix=".json"):
    if not isinstance(model_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", model_id):
        raise ValueError("Invalid model ID for download state")
    return os.path.join(state_dir(), model_id + suffix)


def download_state(model_id):
    path = download_path(model_id)
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    data["running"] = pid_alive(data.get("pid"))
    return data


def write_download_state(model_id, data):
    path = download_path(model_id)
    atomic_json(path, data)


def row_files(row):
    files = []
    have = 0
    need = 0
    for item in row["files"]:
        dest = dest_for(item["path"])
        got = file_bytes(dest)
        partial = file_bytes(dest_for(item["path"] + ".part"))
        need += item["bytes"]
        have += min(max(got, partial), item["bytes"])
        files.append({
            "path": item["path"],
            "bytes": item["bytes"],
            "have": max(got, partial),
            "ready": got == item["bytes"],
            "primary": bool(item.get("primary")),
        })
    return files, have, need


def recommend_id(rows):
    by_id = {row["id"]: row for row in rows}
    if not by_id["qwen38-27b"]["fits"]:
        return "qwen35-9b"
    if not by_id["qwen38-flash-next"]["fits"]:
        return "qwen36-35b-a3b"
    return "qwen38-27b"


def http_json(path, body=None, timeout=3):
    url = "http://%s:%s%s" % (HOST, PORT, path)
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        return {"error": str(exc)}


def server_list():
    data = http_json("/models")
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        return None
    out = {}
    for item in data["data"]:
        if not isinstance(item, dict) or not isinstance(item.get("status"), dict):
            return None
        name, status = item.get("id"), item["status"].get("value")
        if (not isinstance(name, str) or not name or name in out
                or status not in ("loaded", "unloaded", "loading", "unloading")):
            return None
        out[name] = status
    return out


def model_status():
    """Read router activity without consulting or changing the local library."""
    server = server_list()
    if server is None:
        return {"state": "unknown"}
    loaded = [name for name, status in server.items() if status == "loaded"]
    if not loaded:
        return {"state": "empty"}
    unknown = False
    for name in loaded:
        quoted = urllib.parse.quote(name, safe="")
        slots = http_json("/slots?autoload=false&model=" + quoted, timeout=1)
        if not isinstance(slots, list):
            unknown = True
            continue
        for slot in slots:
            if not isinstance(slot, dict) or type(slot.get("is_processing")) is not bool:
                unknown = True
            elif slot["is_processing"]:
                return {"state": "active"}
    return {"state": "unknown" if unknown else "ready"}


def legacy_bindings(rows):
    """Resolve old display-name routes without assigning one name to two files.

    Keep unique legacy names usable by an already-running router. A collided
    name is usable only when an existing, non-duplicate preset binds its path
    to exactly one recipe; never guess which weights a legacy router loaded.
    """
    by_name = {}
    ids = {row["id"] for row in rows}
    for row in rows:
        by_name.setdefault(row["name"], []).append(row)
    saved = configparser.ConfigParser(interpolation=None)
    try:
        with open(preset_path()) as fh:
            saved.read_string("[header]\n" + fh.read())
    except (OSError, configparser.Error):
        saved = configparser.ConfigParser(interpolation=None)
    bindings = {}
    for name, candidates in by_name.items():
        if name in ids:
            continue  # Canonical IDs must never become another recipe's alias.
        if len(candidates) == 1:
            bindings[name] = candidates[0]["id"]
            continue
        path = saved.get(name, "model", fallback="")
        matches = [row for row in candidates if any(
            item.get("primary") and dest_for(item["path"]) == path
            for item in row["files"])]
        if len(matches) == 1:
            bindings[name] = matches[0]["id"]
    return bindings


def router_name(row, server, bindings=None):
    """Prefer stable recipe IDs, retaining an observed active legacy route."""
    if bindings is None:
        bindings = legacy_bindings(all_models()[0])
    model_id, legacy = row["id"], row["name"]
    if (legacy != model_id and legacy in server
            and server[legacy] != "unloaded" and legacy not in bindings
            and legacy not in {item["id"] for item in all_models()[0]}):
        raise ValueError("Ambiguous legacy router name %s; stop the engine before changing these model files." % legacy)
    alias = legacy if bindings.get(legacy) == model_id else None
    for name in (model_id, alias):
        if name is not None and server.get(name, "unloaded") != "unloaded":
            return name
    if model_id in server:
        return model_id
    return alias if alias in server else model_id


def slot_state(name):
    quoted = urllib.parse.quote(name)
    data = http_json("/slots?autoload=false&model=" + quoted, timeout=3)
    generating = False
    if isinstance(data, list):
        generating = any(bool(slot.get("is_processing")) for slot in data if isinstance(slot, dict))
    return generating


def token_count(name):
    quoted = urllib.parse.quote(name)
    url = "http://%s:%s/metrics?autoload=false&model=%s" % (HOST, PORT, quoted)
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            text = resp.read().decode("utf-8", "replace")
    except Exception:
        return None
    for line in text.splitlines():
        if line.startswith("tokens_predicted_total"):
            part = line.split()[-1]
            try:
                return int(float(part))
            except ValueError:
                return None
    return None


def service_ram_gb():
    uid = os.getuid()
    path = "/sys/fs/cgroup/user.slice/user-%s.slice/user@%s.service/app.slice/omastrix-llama.service/memory.current" % (uid, uid)
    try:
        raw = int(open(path).read().strip())
    except (OSError, ValueError):
        return None
    return round(raw / 1024**3, 1)


def status_label(installed, server_status, generating):
    if not installed:
        return "Not Installed"
    if server_status == "loaded" and generating:
        return "Inferring"
    if server_status == "loaded":
        return "Loaded"
    return "Not Loaded"


def parameter_label(row):
    if row.get("parameters"):
        return row["parameters"]
    count = row.get("parameter_count")
    if isinstance(count, (int, float)) and count > 0:
        return "%.0fB" % (count / 1_000_000_000)
    return params_from_name(row["name"]) if row.get("added") else "—"


def read_ledger():
    try:
        with open(ledger_path()) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def library_view(gtt_total_gib):
    models, reserve = all_models()
    server = server_list()
    bindings = legacy_bindings(models)
    rows = []
    for row in models:
        files, have, need = row_files(row)
        installed = all(item["ready"] for item in files)
        weight = need / 1024**3
        need_gib = weight + float(row["kv_gib"]) + reserve
        fits = gtt_total_gib is not None and need_gib <= float(gtt_total_gib)
        shortfall = 0 if fits or gtt_total_gib is None else round(need_gib - float(gtt_total_gib), 1)
        state = download_state(row["id"])
        status = "not_installed"
        if installed:
            status = "installed"
        elif state.get("running") or (have and have < need):
            status = "downloading" if state.get("running") else "partial"
        route, route_error = row["id"], ""
        try:
            if server is not None:
                route = router_name(row, server, bindings)
            server_status = "engine_stopped" if server is None else server.get(route, "unloaded")
        except ValueError as exc:
            server_status, route_error = "unavailable", str(exc)
        speed = row.get("speed") or {}
        rows.append({
            "id": row["id"],
            "name": row["name"],
            "short": row["short"],
            "quant": row["quant"],
            "tags": row["tags"],
            "test": bool(row.get("test")),
            "size_gib": size_label(need),
            "installed": installed,
            "deletable": not state.get("running") and any(item["have"] > 0 for item in files),
            "status": status,
            "have_bytes": have,
            "need_bytes": need,
            "fits": fits,
            "shortfall_gib": shortfall,
            "weight_gib": round(weight, 2),
            "kv_gib": row["kv_gib"],
            "reserve_gib": reserve,
            "ctx": row["ctx"],
            "server_status": server_status,
            "router_name": route,
            "speed": ("%s tok/s %s, %s" % (speed["tok_s"], speed["kind"], speed["machine"])) if speed else "",
            "error": route_error or state.get("error") or "",
            "added": bool(row.get("added")),
            "params": parameter_label(row),
        })
    rec = recommend_id(rows)
    for row in rows:
        row["recommended"] = row["id"] == rec
    fitting = [row for row in rows if row["fits"]]
    too_large = [row for row in rows if not row["fits"]]
    fitting.sort(key=lambda row: (0 if row["recommended"] else 1, rows.index(row)))
    loaded = next((row for row in rows if row["server_status"] == "loaded"), None)
    generating = False
    tokens = None
    if loaded:
        generating = slot_state(loaded["router_name"])
        tokens = token_count(loaded["router_name"])
    ram = service_ram_gb() if loaded else None
    for row in rows:
        row["engine_name"] = "strix-llama.cpp"
        row["status_label"] = status_label(row["installed"], row["server_status"], generating and row is loaded)
        row["ram"] = ("%s GiB" % ram) if row["server_status"] == "loaded" and ram is not None else "—"
        row["size"] = "%s GiB" % row["size_gib"]
        need = row["need_bytes"] or 0
        have = row["have_bytes"] or 0
        row["progress"] = 0 if not need else min(100, int(round(100 * have / need)))
        if row["status"] == "downloading":
            row["notes"] = "%s%%  %s GiB of %s GiB" % (row["progress"], size_label(have), size_label(need))
        elif gtt_total_gib is None:
            row["notes"] = "GTT ceiling unavailable"
        elif not row["fits"]:
            row["notes"] = "Too large for this system by %s GiB" % row["shortfall_gib"]
        elif row.get("added"):
            row["notes"] = "Added from a link. Context memory is estimated."
        else:
            row["notes"] = "—"
    ordered = fitting + too_large
    return {
        "root": models_root(),
        "reserve_gib": reserve,
        "recommended": rec,
        "fitting": fitting,
        "too_large": too_large,
        "rows": ordered,
        "loaded_id": loaded["id"] if loaded else "",
        "loaded_name": loaded["name"] if loaded else "",
        "loaded_short": loaded["short"] if loaded else "",
        "generating": generating,
        "tokens_since_load": tokens,
        "tokens_note": "" if tokens is not None or not loaded else "Token count unavailable",
    }


def preset_text(gtt_total_gib=None):
    rows, reserve = all_models()
    bindings = legacy_bindings(rows)
    lines = [
        "version = 1",
        "",
        "[*]",
        "n-gpu-layers = all",
        "flash-attn = on",
        "load-mode = none",
        "fit = off",
        "parallel = 1",
        "jinja = true",
        "",
    ]
    for row in rows:
        files, _have, need = row_files(row)
        if not all(item["ready"] for item in files):
            continue
        if gtt_total_gib is not None:
            need_gib = need / 1024**3 + float(row["kv_gib"]) + reserve
            if need_gib > float(gtt_total_gib):
                continue
        primary = next(item for item in row["files"] if item.get("primary"))
        # IDs are canonical. Retained aliases keep a live legacy router/preset
        # usable during periodic snapshots; writing never reloads the router.
        names = [row["id"]] + [name for name, model_id in bindings.items()
                                 if model_id == row["id"]]
        for name in names:
            lines.append("[%s]" % name)
            lines.append("model = %s" % dest_for(primary["path"]))
            lines.append("ctx-size = %s" % row["ctx"])
            for key, value in (row.get("serve") or {}).items():
                lines.append("%s = %s" % (key, value))
            lines.append("")
    return "\n".join(lines)


def write_preset(gtt_total_gib=None):
    path = preset_path()
    atomic_text(path, preset_text(gtt_total_gib), reject_symlink=True)
    return path


def reload_server():
    return http_json("/models?reload=1", timeout=8)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def params_from_name(name):
    match = re.search(r"(\d+(?:\.\d+)?)B", name, re.I)
    if not match:
        return "—"
    return match.group(1) + "B"


def normalize_gguf_url(raw):
    text = (raw or "").strip()
    if not text:
        return "", "Paste a direct link to one .gguf file."
    try:
        parsed = urllib.parse.urlsplit(text)
    except ValueError:
        return "", "Invalid model URL."
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return "", "The link has to be an https link to one .gguf file."
    path = parsed.path
    host = (parsed.hostname or "").lower()
    if (host == "huggingface.co" or host.endswith(".huggingface.co")) and "/blob/" in path:
        path = path.replace("/blob/", "/resolve/", 1)
    filename = os.path.basename(urllib.parse.unquote(path))
    if not filename.lower().endswith(".gguf"):
        return "", "That is not a direct link to a .gguf file. A model page is not enough."
    if re.search(r"\d+-of-\d+", filename, re.I):
        return "", "That file is one piece of a split model. Paste one complete .gguf file."
    if "mmproj" in filename.lower():
        return "", "A vision projector is not a text model."
    safe = re.sub(r"[^A-Za-z0-9._+-]", "_", filename)
    if not safe.lower().endswith(".gguf") or safe == ".gguf":
        return "", "That file name cannot be saved."
    url = urllib.parse.urlunsplit(("https", parsed.netloc, path, parsed.query, ""))
    return url, ""


def remote_size(url):
    try:
        out = subprocess.run(
            ["curl", "-fsI", "-L", "--max-redirs", "5", "--retry", "2", "--max-time", "30", url],
            capture_output=True, text=True, timeout=40, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if out.returncode != 0:
        return 0
    size = 0
    for line in (out.stdout or "").splitlines():
        if line.lower().startswith("content-length:"):
            try:
                size = int(line.split(":", 1)[1].strip())
            except ValueError:
                size = 0
    return size


@serialized("added", wait=True)
def remember_added_file(model_id, rel, nbytes, digest):
    models = load_added()
    changed = False
    for row in models:
        if row.get("id") != model_id:
            continue
        for item in row.get("files") or []:
            if item.get("path") == rel:
                item["bytes"] = nbytes
                item["sha256"] = digest
                changed = True
    if not changed:
        raise ValueError("Could not find the added model to record its verified hash")
    save_added(models)
    return {"success": True}


@serialized("added")
def add_from_url(raw):
    url, err = normalize_gguf_url(raw)
    if err:
        return {"success": False, "error": err}
    catalog, _reserve = load_catalog()
    for row in catalog:
        for item in row.get("files") or []:
            if item.get("url") == url:
                return {"success": False, "error": row["name"] + " is already in the list."}
    added = load_added()
    for row in added:
        for item in row.get("files") or []:
            if item.get("url") == url:
                return {"success": True, "id": row["id"], "message": row["name"] + " is already in the library."}
    size = remote_size(url)
    if size <= 0:
        return {"success": False, "error": "The link did not report a file size. Use a direct https link to one .gguf file."}
    raw_name = os.path.basename(urllib.parse.unquote(urllib.parse.urlsplit(url).path))
    stem = re.sub(r"[^A-Za-z0-9._+-]", "_", raw_name[:-5])[:175]
    filename = stem + ".gguf"
    model_id = "link-" + hashlib.sha256(url.encode()).hexdigest()[:12]
    row = {
        "id": model_id,
        "name": stem[:80],
        "short": params_from_name(stem),
        "quant": "",
        "tags": ["Added"],
        "test": False,
        "ctx": 8192,
        "kv_gib": 1,
        "files": [{
            "path": "added/%s/%s" % (model_id, filename),
            "bytes": size,
            "sha256": "",
            "url": url,
            "primary": True,
        }],
        "serve": {},
        "added": True,
    }
    added.append(row)
    save_added(added)
    return {
        "success": True,
        "id": model_id,
        "message": row["name"] + " added to the library.",
    }


@serialized("downloads", wait=True, worker=True,
            error_state=lambda model_id: download_path(model_id))
def fetch(model_id):
    row, _reserve = find_model(model_id)
    if row is None:
        print(json.dumps({"success": False, "error": "Unknown model"}))
        return 2
    write_download_state(model_id, {"pid": os.getpid(), "error": ""})
    server = server_list()
    if server is None:
        probe = subprocess.run(
            ["systemctl", "--user", "is-active", "omastrix-llama.service"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if service_state(probe.returncode, (probe.stdout or "").strip()) not in ("stopped", "failed"):
            raise ValueError("Cannot confirm engine state; no model files were changed")
    elif server.get(router_name(row, server), "unloaded") != "unloaded":
        raise ValueError("Unload this model before downloading or verifying its files")
    os.makedirs(models_root(), exist_ok=True)
    for item in row["files"]:
        dest = dest_for(item["path"])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        partial = dest_for(item["path"] + ".part")
        if os.path.isfile(dest) and file_bytes(dest) != item["bytes"]:
            os.replace(dest, partial)
        candidate = dest if file_bytes(dest) == item["bytes"] else partial
        code = 0
        if file_bytes(candidate) != item["bytes"]:
            proc = subprocess.run(
                [
                    "curl", "-q", "--proto", "=https", "--proto-redir", "=https",
                    "-L", "--fail", "--retry", "8", "--retry-all-errors",
                    "--continue-at", "-", "-o", partial, item["url"],
                ],
                check=False,
            )
            code = proc.returncode
        if code != 0 or file_bytes(candidate) != item["bytes"]:
            write_download_state(model_id, {
                "pid": 0,
                "error": "Download stopped before the file reached %s bytes" % item["bytes"],
            })
            print(json.dumps({"success": False, "error": "Download incomplete"}))
            return 1
        digest = sha256_file(candidate)
        expected = item.get("sha256") or ""
        if expected and digest != expected:
            if candidate == dest:
                os.replace(dest, partial)
            os.remove(partial)
            write_download_state(model_id, {
                "pid": 0,
                "error": "Downloaded file hash does not match the catalog",
            })
            print(json.dumps({"success": False, "error": "Hash mismatch"}))
            return 1
        if not expected:
            recorded = remember_added_file(model_id, item["path"], file_bytes(candidate), digest)
            if recorded.get("success") is not True:
                raise ValueError(recorded.get("error") or "Could not record model hash")
        if candidate != dest:
            os.replace(candidate, dest)
    write_download_state(model_id, {"pid": 0, "error": ""})
    print(json.dumps({"success": True, "message": row["name"] + " installed."}))
    return 0


@serialized("downloads")
def start_download(model_id):
    row, _reserve = find_model(model_id)
    if row is None:
        return {"success": False, "error": "Unknown model"}
    # A size match does not prove integrity. The worker verifies existing files too.
    state = download_state(model_id)
    if state.get("running"):
        return {"success": True, "message": row["name"] + " is already downloading."}
    with open(download_path(model_id, ".log"), "ab") as log:
        proc = subprocess.Popen(
            [os.path.join(root_dir(), "bin/omastrix"), "library-fetch", model_id],
            start_new_session=True,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    write_download_state(model_id, {"pid": proc.pid, "error": ""})
    return {"success": True, "message": "Downloading " + row["name"] + " into ~/models."}


def loaded_name():
    server = server_list()
    if not server:
        return None
    for name, status in server.items():
        if status == "loaded":
            return name
    return None


def ensure_engine():
    state = subprocess.run(
        ["systemctl", "--user", "is-active", "omastrix-llama.service"],
        capture_output=True, text=True, timeout=15, check=False,
    )
    if (state.stdout or "").strip() != "active":
        started = subprocess.run(
            ["systemctl", "--user", "start", "omastrix-llama.service"],
            capture_output=True, text=True, timeout=20, check=False,
        )
        if started.returncode != 0:
            err = (started.stderr or started.stdout or "").strip()
            return False, err or "strix-llama.cpp did not start."
    deadline = time.time() + 25
    while time.time() < deadline:
        if server_list() is not None:
            return True, ""
        time.sleep(0.4)
    return False, "strix-llama.cpp did not open port 8080."


def unload_name(name):
    return http_json("/models/unload", {"model": name}, timeout=30)


# Lock order for combined operations: engine -> router -> downloads -> added.
# Never wait for an earlier lock while holding a later one. Engine installers
# hold only engine; fetch workers hold downloads (then added for saved hashes).
@serialized("engine")
@serialized("router")
@serialized("downloads")
def load_checked(model_id, gtt_total_gib, confirm):
    row, reserve = find_model(model_id)
    if row is None:
        return {"success": False, "id": model_id, "error": "Unknown model"}
    files, _have, need = row_files(row)
    if not all(item["ready"] for item in files):
        return {"success": False, "id": model_id, "error": row["name"] + " is not installed."}
    weight = need / 1024**3
    need_gib = weight + float(row["kv_gib"]) + reserve
    if gtt_total_gib is None or need_gib > float(gtt_total_gib):
        shortfall = None if gtt_total_gib is None else round(need_gib - float(gtt_total_gib), 1)
        return {
            "success": False,
            "id": model_id,
            "error": "%s does not fit. Weight %.1f GiB, KV %.1f GiB, desktop reserve %.0f GiB, shortfall %s GiB." % (
                row["name"], weight, row["kv_gib"], reserve, shortfall if shortfall is not None else "?",
            ),
        }
    for item in row["files"]:
        expected = item.get("sha256")
        if not expected or sha256_file(dest_for(item["path"])) != expected:
            return {"success": False, "id": model_id, "error": "Model hash verification failed; install the model again."}
    server = server_list()
    if server is None:
        ok, err = ensure_engine()
        if not ok:
            return {"success": False, "id": model_id, "error": err}
        server = server_list()
    if server is None or any(status not in ("loaded", "unloaded") for status in server.values()):
        return {"success": False, "id": model_id, "error": "Cannot load while router state is unavailable or a model is loading/unloading."}
    current = next((name for name, status in server.items() if status == "loaded"), "")
    target = router_name(row, server)
    if current == target:
        return {"success": True, "id": model_id, "message": row["name"] + " is already loaded."}
    if current and current != target and not confirm:
        return {
            "success": False,
            "needs_confirm": True,
            "id": model_id,
            "error": "Load will unload %s first. Click Load again." % current,
        }
    write_preset(gtt_total_gib)
    if current and current != target:
        result = unload_name(current)
        if result.get("error"):
            return {"success": False, "id": model_id, "error": result["error"]}
        if not wait_unloaded(current):
            return {"success": False, "id": model_id, "error": "Previous model did not unload."}
    if target not in (server_list() or {}):
        reload_server()
    quoted = urllib.parse.quote(target)
    result = http_json("/props?model=" + quoted, timeout=600)
    if result.get("error"):
        return {"success": False, "id": model_id, "error": result["error"]}
    if (server_list() or {}).get(target) != "loaded":
        return {"success": False, "id": model_id, "error": "Engine did not confirm the model loaded."}
    return {"success": True, "id": model_id, "message": row["name"] + " loaded."}


def wait_unloaded(name, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        server = server_list()
        if server is not None and (name not in server or server[name] == "unloaded"):
            return True
        time.sleep(0.4)
    return False


@serialized("router")
def unload_model(model_id):
    row, _reserve = find_model(model_id)
    server = server_list()
    if server is None:
        return {"success": False, "error": "strix-llama.cpp is not running."}
    name = router_name(row, server) if row else model_id
    if server.get(name) != "loaded":
        return {"success": True, "message": name + " is not loaded."}
    result = unload_name(name)
    if result.get("error"):
        return {"success": False, "error": result["error"]}
    if not wait_unloaded(name):
        return {"success": False, "error": name + " did not unload."}
    return {"success": True, "message": name + " unloaded."}


def catalog_paths(row):
    paths = []
    for item in row["files"]:
        for rel in (item["path"], item["path"] + ".part"):
            dest = dest_for(rel)
            if os.path.isfile(dest):
                paths.append(dest)
    return paths


def remove_catalog_file(dest):
    root = os.path.realpath(models_root())
    real = os.path.realpath(dest)
    if real != root and not real.startswith(root + os.sep):
        raise ValueError("refusing to delete outside ~/models")
    if os.path.islink(dest) or not os.path.isfile(dest):
        raise ValueError("refusing to delete a non-file")
    os.remove(dest)


def prune_empty_dirs(start):
    root = os.path.realpath(models_root())
    path = os.path.realpath(start)
    while path != root and path.startswith(root + os.sep):
        try:
            if os.listdir(path):
                return
            os.rmdir(path)
        except OSError:
            return
        path = os.path.dirname(path)


def stop_download(model_id):
    state = download_state(model_id)
    raw_pid = state.get("pid")
    if not isinstance(raw_pid, int) or not pid_alive(raw_pid):
        write_download_state(model_id, {"pid": 0, "error": ""})
        return
    pid = raw_pid
    try:
        raw = open("/proc/%s/cmdline" % pid, "rb").read()
    except OSError:
        write_download_state(model_id, {"pid": 0, "error": ""})
        return
    parts = raw.split(b"\x00")
    cmd = [part.decode("utf-8", "replace") for part in parts if part]
    if "library-fetch" not in cmd or model_id not in cmd:
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + 5
    while time.time() < deadline and pid_alive(pid):
        time.sleep(0.1)
    if pid_alive(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass
    write_download_state(model_id, {"pid": 0, "error": ""})


@serialized("router")
@serialized("downloads")
def delete_model(model_id, gtt_total_gib, confirm):
    row, _reserve = find_model(model_id)
    if row is None:
        return {"success": False, "id": model_id, "error": "Unknown model"}
    running = download_state(model_id).get("running")
    if running:
        return {"success": False, "id": model_id, "error": "Wait for the download to finish before deleting this model."}
    present = catalog_paths(row)
    if not present:
        return {"success": False, "id": model_id, "error": row["name"] + " is not installed."}
    server = server_list()
    target = router_name(row, server) if server is not None else row["id"]
    loaded_this = server is not None and server.get(target) == "loaded"
    if not confirm:
        if loaded_this:
            msg = "Delete will unload %s and remove its files from ~/models. Click Delete again." % row["name"]
        else:
            msg = "Delete will remove %s from ~/models. Click Delete again." % row["name"]
        return {
            "success": False,
            "needs_confirm": True,
            "confirm": "delete",
            "id": model_id,
            "error": msg,
        }
    if server is None:
        try:
            service = subprocess.run(
                ["systemctl", "--user", "is-active", "omastrix-llama.service"],
                capture_output=True, text=True, timeout=15, check=False,
            )
            stopped = service_state(service.returncode, (service.stdout or "").strip()) in ("stopped", "failed")
        except (OSError, subprocess.SubprocessError):
            stopped = False
        if not stopped:
            return {"success": False, "id": model_id, "error": "Cannot confirm engine state; files were not deleted."}
    elif server.get(target, "unloaded") not in ("loaded", "unloaded"):
        return {"success": False, "id": model_id, "error": "Model is loading or unloading; files were not deleted."}

    if loaded_this:
        result = unload_name(target)
        if result.get("error"):
            return {"success": False, "id": model_id, "error": "Could not unload before delete: " + result["error"]}
        if not wait_unloaded(target):
            return {"success": False, "id": model_id, "error": "Model is still unloading; files were not deleted."}
    removed = 0
    parents = []
    for dest in catalog_paths(row):
        remove_catalog_file(dest)
        removed += 1
        parents.append(os.path.dirname(dest))
    for parent in sorted(parents, key=len, reverse=True):
        prune_empty_dirs(parent)
    write_download_state(model_id, {"pid": 0, "error": ""})
    write_preset(gtt_total_gib)
    if server is not None and not loaded_name():
        reload_server()
    return {
        "success": True,
        "id": model_id,
        "removed": removed,
        "message": row["name"] + " removed from ~/models.",
    }


def main(argv):
    verb = argv[1] if len(argv) > 1 else ""
    if verb == "library-fetch" and len(argv) > 2:
        return fetch(argv[2])
    print("library helper", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
