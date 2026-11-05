// Pure presentation rules, shared by QML and the Node test runner.
function actionName(text, context) {
  return context ? text + " " + context : text;
}

function formatGttUsed(value) {
  if ((typeof value !== "number" && typeof value !== "string") || String(value).trim() === "") return "—";
  var used = Number(value);
  return isFinite(used) && used >= 0 ? used.toFixed(1) : "—";
}

function serviceState(info) {
  var state = info.state || "";
  var labels = {running: "Running", stopped: "Stopped", failed: "Failed",
    starting: "Starting…", stopping: "Stopping…", installing: "Installing…",
    not_installed: "Not installed"};
  var working = info.updating === true || ["starting", "stopping", "installing"].indexOf(state) >= 0;
  var text = info.updating === true ? (info.installed ? "Updating…" : "Installing…") : (labels[state] || "Unavailable");
  var stopped = state === "stopped" || state === "failed";
  return {text: text, working: working, stopped: stopped,
    primaryEnabled: !working && (info.installed ? (stopped || state === "running") : state === "not_installed")};
}

function serviceDetail(info, isEngine) {
  var version = isEngine ? (info.build ? "Build " + info.build : "") : (info.version || "");
  var latest = isEngine ? info.latest_build : info.latest_version;
  var installed = isEngine ? info.build : info.version;
  if (info.update_available) return version + " · " + (isEngine ? "Build " : "") + latest + " available";
  if (latest && installed && latest === installed) return version + " · Up to date";
  return version;
}

function modelAction(row, engineRunning) {
  if (!row.installed) {
    var downloading = row.status === "downloading";
    return {text: downloading ? "Installing…" : "Install", verb: "library-download", enabled: !downloading};
  }
  var loaded = row.status_label === "Loaded" || row.status_label === "Inferring";
  return {text: loaded ? "Unload" : "Load", verb: loaded ? "library-unload" : "library-load",
          enabled: engineRunning && (loaded || row.fits === true)};
}

function commandResult(raw, stderr, exitCode, exitStatus) {
  var body = String(raw || "").trim();
  var error = String(stderr || "").trim();
  var info;
  try { info = JSON.parse(body); } catch (_) {
    return { success: false, error: error || "Command failed. Try again or check the logs." };
  }
  if (!info || typeof info !== "object" || Array.isArray(info))
    return { success: false, error: "Invalid command response." };
  // QProcess::ExitStatus: NormalExit = 0, CrashExit = 1. A normal
  // exit code of 1 is also the backend's explicit confirmation response.
  if (exitStatus === 1)
    return { success: false, error: error || "Command crashed. Try again or check the logs." };
  if (info.needs_confirm === true && (exitCode === 0 || exitCode === 1)) return info;
  if (exitCode !== 0 || info.success !== true)
    return { success: false, error: info.error || error || "Command failed. Try again or check the logs." };
  return info;
}
