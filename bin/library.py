"""Starter library. Reads ~/models. Does not download or load unless a verb asks."""

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request

RESERVE_GIB = 14
HOST = "127.0.0.1"
PORT = 8080


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


def save_added(models):
    os.makedirs(os.path.dirname(added_path()), exist_ok=True)
    with open(added_path(), "w") as fh:
        json.dump({"models": models}, fh, indent=2)
        fh.write("\n")


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
    root = os.path.realpath(models_root())
    dest = os.path.realpath(os.path.join(root, rel))
    if dest != root and not dest.startswith(root + os.sep):
        raise ValueError("model path escapes ~/models")
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


def download_state(model_id):
    path = os.path.join(state_dir(), model_id + ".json")
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    data["running"] = pid_alive(data.get("pid"))
    return data


def write_download_state(model_id, data):
    path = os.path.join(state_dir(), model_id + ".json")
    with open(path, "w") as fh:
        json.dump(data, fh)


def row_files(row):
    files = []
    have = 0
    need = 0
    for item in row["files"]:
        dest = dest_for(item["path"])
        got = file_bytes(dest)
        need += item["bytes"]
        have += min(got, item["bytes"])
        files.append({
            "path": item["path"],
            "bytes": item["bytes"],
            "have": got,
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
    if "data" not in data:
        return None
    out = {}
    for item in data.get("data") or []:
        if not isinstance(item, dict):
            continue
        status = ((item.get("status") or {}).get("value")) or "unloaded"
        out[item.get("id") or ""] = status
    return out


def slot_state(name):
    quoted = urllib.parse.quote(name)
    data = http_json("/slots?model=" + quoted, timeout=3)
    generating = False
    if isinstance(data, list):
        generating = any(bool(slot.get("is_processing")) for slot in data if isinstance(slot, dict))
    return generating


def token_count(name):
    quoted = urllib.parse.quote(name)
    url = "http://%s:%s/metrics?model=%s" % (HOST, PORT, quoted)
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


PARAMS = {
    "qwen35-4b": "4B",
    "qwen35-9b": "9B",
    "qwen36-35b-a3b": "35B",
    "qwen38-27b": "27B",
    "qwen38-flash-next": "56B",
    "deepseek-v4-flash": "8.4B",
}


def read_ledger():
    try:
        with open(ledger_path()) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def library_view(gtt_total_gib):
    models, reserve = all_models()
    server = server_list()
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
        server_status = "engine_stopped" if server is None else server.get(row["name"], "unloaded")
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
            "deletable": any(item["have"] > 0 for item in files) or bool(state.get("running")),
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
            "speed": ("%s tok/s %s, %s" % (speed["tok_s"], speed["kind"], speed["machine"])) if speed else "",
            "error": state.get("error") or "",
            "added": bool(row.get("added")),
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
        generating = slot_state(loaded["name"])
        tokens = token_count(loaded["name"])
    ram = service_ram_gb() if loaded else None
    for row in rows:
        row["params"] = PARAMS.get(row["id"], row["short"])
        row["engine_name"] = "strix-llama.cpp"
        row["status_label"] = status_label(row["installed"], row["server_status"], generating and row is loaded)
        row["ram"] = ("%s GB" % ram) if row["server_status"] == "loaded" and ram is not None else "—"
        row["size"] = "%s GB" % row["size_gib"]
        need = row["need_bytes"] or 0
        have = row["have_bytes"] or 0
        row["progress"] = 0 if not need else min(100, int(round(100 * have / need)))
        if row["status"] == "downloading":
            row["notes"] = "%s%%  %s GB of %s GB" % (row["progress"], size_label(have), size_label(need))
        elif not row["fits"]:
            row["notes"] = "Too large for this system by %s GB" % row["shortfall_gib"]
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
        lines.append("[%s]" % row["name"])
        lines.append("model = %s" % dest_for(primary["path"]))
        lines.append("ctx-size = %s" % row["ctx"])
        for key, value in (row.get("serve") or {}).items():
            lines.append("%s = %s" % (key, value))
        lines.append("")
    return "\n".join(lines)


def write_preset(gtt_total_gib=None):
    os.makedirs(os.path.dirname(preset_path()), exist_ok=True)
    text = preset_text(gtt_total_gib)
    current = ""
    try:
        with open(preset_path()) as fh:
            current = fh.read()
    except OSError:
        current = ""
    if current != text:
        with open(preset_path(), "w") as fh:
            fh.write(text)
    return preset_path()


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
    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return "", "The link has to be an https link to one .gguf file."
    path = parsed.path
    host = parsed.netloc.lower()
    if host.endswith("huggingface.co") and "/blob/" in path:
        path = path.replace("/blob/", "/resolve/", 1)
    filename = os.path.basename(path)
    if not filename.lower().endswith(".gguf"):
        return "", "That is not a direct link to a .gguf file. A model page is not enough."
    if re.search(r"\d+-of-\d+", filename):
        return "", "That file is one piece of a split model. Paste one complete .gguf file."
    safe = re.sub(r"[^A-Za-z0-9._+-]", "_", filename)
    if not safe.lower().endswith(".gguf") or safe == ".gguf":
        return "", "That file name cannot be saved."
    url = urllib.parse.urlunsplit(("https", parsed.netloc, path, "", ""))
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
    if changed:
        save_added(models)


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
                return {"success": True, "id": row["id"], "message": row["name"] + " is already in the list. It is not loaded."}
    size = remote_size(url)
    if size <= 0:
        return {"success": False, "error": "The link did not report a file size. Use a direct https link to one .gguf file."}
    filename = re.sub(r"[^A-Za-z0-9._+-]", "_", os.path.basename(urllib.parse.urlsplit(url).path))[:180]
    stem = filename[:-5]
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
        "message": row["name"] + " was added. It is not downloaded and it is not loaded.",
    }


def fetch(model_id):
    row, _reserve = find_model(model_id)
    if row is None:
        print(json.dumps({"success": False, "error": "Unknown model"}))
        return 2
    write_download_state(model_id, {"pid": os.getpid(), "error": ""})
    os.makedirs(models_root(), exist_ok=True)
    for item in row["files"]:
        dest = dest_for(item["path"])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if file_bytes(dest) == item["bytes"]:
            continue
        proc = subprocess.run(
            [
                "curl", "-L", "--fail", "--retry", "8", "--retry-all-errors",
                "--continue-at", "-", "-o", dest, item["url"],
            ],
            check=False,
        )
        if proc.returncode != 0 or file_bytes(dest) != item["bytes"]:
            write_download_state(model_id, {
                "pid": 0,
                "error": "Download stopped before the file reached %s bytes" % item["bytes"],
            })
            print(json.dumps({"success": False, "error": "Download incomplete"}))
            return 1
        digest = sha256_file(dest)
        expected = item.get("sha256") or ""
        if expected and digest != expected:
            write_download_state(model_id, {
                "pid": 0,
                "error": "Downloaded file hash does not match the catalog",
            })
            print(json.dumps({"success": False, "error": "Hash mismatch"}))
            return 1
        if not expected:
            remember_added_file(model_id, item["path"], file_bytes(dest), digest)
    write_download_state(model_id, {"pid": 0, "error": ""})
    print(json.dumps({"success": True, "message": row["name"] + " is installed. It is not loaded."}))
    return 0


def start_download(model_id):
    row, _reserve = find_model(model_id)
    if row is None:
        return {"success": False, "error": "Unknown model"}
    files, _have, _need = row_files(row)
    if all(item["ready"] for item in files):
        return {"success": True, "message": row["name"] + " is already installed. Download did not run."}
    state = download_state(model_id)
    if state.get("running"):
        return {"success": True, "message": row["name"] + " is already downloading."}
    log = open(os.path.join(state_dir(), model_id + ".log"), "ab")
    proc = subprocess.Popen(
        [os.path.join(root_dir(), "bin/omastrix"), "library-fetch", model_id],
        start_new_session=True,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    write_download_state(model_id, {"pid": proc.pid, "error": ""})
    return {"success": True, "message": "Downloading " + row["name"] + " into ~/models. It will not load."}


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
    server = server_list()
    if server is None:
        ok, err = ensure_engine()
        if not ok:
            return {"success": False, "id": model_id, "error": err}
        server = server_list() or {}
    current = next((name for name, status in server.items() if status == "loaded"), "")
    if current and current != row["name"] and not confirm:
        return {
            "success": False,
            "needs_confirm": True,
            "id": model_id,
            "error": "Load will unload %s first. Click Load again." % current,
        }
    write_preset(gtt_total_gib)
    if current and current != row["name"]:
        unload_name(current)
    if row["name"] not in (server_list() or {}):
        reload_server()
    quoted = urllib.parse.quote(row["name"])
    result = http_json("/props?model=" + quoted, timeout=600)
    if result.get("error"):
        return {"success": False, "id": model_id, "error": result["error"]}
    return {"success": True, "id": model_id, "message": row["name"] + " loaded."}


def unload_model(model_id):
    row, _reserve = find_model(model_id)
    name = row["name"] if row else model_id
    server = server_list()
    if server is None:
        return {"success": False, "error": "strix-llama.cpp is not running."}
    if server.get(name) != "loaded":
        return {"success": True, "message": name + " is not loaded."}
    result = unload_name(name)
    if result.get("error"):
        return {"success": False, "error": result["error"]}
    return {"success": True, "message": name + " unloaded."}


def catalog_paths(row):
    paths = []
    for item in row["files"]:
        dest = dest_for(item["path"])
        if os.path.isfile(dest) and not os.path.islink(dest):
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


def delete_model(model_id, gtt_total_gib, confirm):
    row, _reserve = find_model(model_id)
    if row is None:
        return {"success": False, "id": model_id, "error": "Unknown model"}
    present = catalog_paths(row)
    running = download_state(model_id).get("running")
    if not present and not running:
        return {"success": False, "id": model_id, "error": row["name"] + " is not installed."}
    server = server_list()
    loaded = ""
    if server:
        loaded = next((name for name, status in server.items() if status == "loaded"), "")
    loaded_this = loaded == row["name"]
    if not confirm:
        if loaded_this:
            msg = "Delete will unload %s and remove its files from ~/models. Click Delete again." % row["name"]
        elif running:
            msg = "Delete will stop the download and remove %s from ~/models. Click Delete again." % row["name"]
        else:
            msg = "Delete will remove %s from ~/models. Click Delete again." % row["name"]
        return {
            "success": False,
            "needs_confirm": True,
            "confirm": "delete",
            "id": model_id,
            "error": msg,
        }
    if running:
        stop_download(model_id)
    if loaded_this:
        result = unload_name(row["name"])
        if result.get("error"):
            return {"success": False, "id": model_id, "error": "Could not unload before delete: " + result["error"]}
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
        "message": row["name"] + " was removed from ~/models. It is not loaded.",
    }


def main(argv):
    verb = argv[1] if len(argv) > 1 else ""
    if verb == "library-fetch" and len(argv) > 2:
        return fetch(argv[2])
    print("library helper", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
