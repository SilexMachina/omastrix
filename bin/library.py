"""Starter library. Reads ~/models. Does not download or load unless a verb asks."""

import hashlib
import json
import os
import subprocess
import sys
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


def find_model(model_id):
    models, reserve = load_catalog()
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
    models, reserve = load_catalog()
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
        if not row["fits"]:
            row["notes"] = "Too large for this system by %s GB" % row["shortfall_gib"]
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
    rows, reserve = load_catalog()
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
        if digest != item["sha256"]:
            write_download_state(model_id, {
                "pid": 0,
                "error": "Downloaded file hash does not match the catalog",
            })
            print(json.dumps({"success": False, "error": "Hash mismatch"}))
            return 1
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
        return {"success": False, "id": model_id, "error": "Start strix-llama.cpp before loading a model."}
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


def main(argv):
    verb = argv[1] if len(argv) > 1 else ""
    if verb == "library-fetch" and len(argv) > 2:
        return fetch(argv[2])
    print("library helper", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
