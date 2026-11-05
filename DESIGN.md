# Design

OmaStrix is an Omarchy bar plugin for local text inference on Strix Halo.
Display name: **OmaStrix**. Subtitle: **Local AI for Strix Halo**.
Install ID: `silexmachina.omastrix`.

This is the implementation contract, not proof that every acceptance check has
passed. [Release readiness](docs/releasing.md) records the remaining gates;
[setup limits](docs/user-guide.md#setup-status) distinguish the development
workflow from a verified fresh install.

## Architecture

| Component | Responsibility |
| --- | --- |
| `View.js` | Pure service/model presentation and command-result validation helpers. |
| `Panel.qml` | Themed bar pill and panel; dispatch explicit actions and render backend state. |
| `bin/omastrix` | Host/GTT snapshot, engine control and updates, command dispatch; JSON interface. |
| `bin/library.py` | Catalog, fit checks, presets, downloads, load/unload and selected-file deletion. |
| `bin/webui.py` | Separate OmaStrix Open WebUI install and service lifecycle. |
| `bin/omastrix-engine-install` | Build the approved engine commit into the user's profile. |
| `catalog.json` | Shipped recipes, paths, expected sizes/hashes, context and serve flags. |
| `engine-pin.json` | Reproducible engine source/baseline commit, independent of plugin version. |
| `manifest.json` | Plugin identity, settings, and single source of current version. |

The backend owns host probes, fit decisions, file operations, and service/API
calls. QML must not infer success from a click or implement a second fit policy.
Snapshot refreshes may maintain local presets/state but must not load or fetch
weights. `View.js` provides pure presentation helpers; it does not replace
backend fit checks or service guards. Snapshot `app_version` comes from the
manifest, not a separate hardcoded UI version.

## Execution boundaries

- One native `halo-box/strix-llama.cpp` engine using Vulkan/RADV; not Docker,
  Ollama, stock llama.cpp, or a multi-engine manager.
- OmaStrix's full-path wrapper starts a loopback router on `127.0.0.1:8080`,
  `--models-max 1`, explicit presets, and `--offline`; no model path at start.
  Presets use `load-mode = none`. Logon start defaults off; no linger.
- Normal Install and Update resolve the newest published Halo `b`-number tag
  and compile its exact commit, never floating `main`. First install does not
  silently fall back to a stale baseline if discovery fails. Preserve installed
  engines unless Update is explicitly selected. `engine-pin.json` remains an
  unchanged reproducible baseline for development.
- Build/install/update must leave services stopped. Require the user to stop a
  running service before replacement; no hidden stop, start, or restart.
- RADV environment applies only to supported OmaStrix engine processes.
- A single preview build runs the panel on other hardware. Engine installation,
  WebUI and model downloads remain available. Unsupported hosts skip Strix
  GPU/heap acceptance and record that verification is unavailable; startup,
  model loading and GTT changes remain blocked in backend and UI.
- Open WebUI is optional, with an independent install and user service. Fresh
  installs bind to `127.0.0.1:3000`. The panel offers This device / Local network
  access while stopped. Network access binds `0.0.0.0`, requires confirmation and
  an existing administrator in the product SQLite database. A wrapper guard
  checks this again at launch. Authentication stays on and signup stays off.
  First-account setup happens locally; custom database network bootstrap is
  unsupported. Existing network configurations are preserved, subject to the guard.

## Panel contract

Use the 1180 px preferred-width panel, clamped to the available screen, with two
clear sections: **System** then **Models**, not a dashboard of cards.
Use Omarchy `qs.Ui`/`qs.Commons` components and theme colors, fonts, spacing,
focus, hover, and disabled states. Do not hardcode a private color palette.

### System

On unsupported hardware, show **Hardware Unsupported - strix-llama.cpp will not function**
to the right of the title, using the urgent theme color and prominent text.
Keep both panes visible. Once installed, the engine Start button is urgent-colored
and disabled; Install remains available. This is the same distribution as the
Strix Halo build, with no test-mode switch.

Include an OmaStrix update row above the service rows. Manual Check updates
fetches the installed checkout's origin/default HEAD and compares revisions;
Update launches `omarchy plugin update silexmachina.omastrix --yes` asynchronously.
Protect local modifications and divergent history, persist update errors/status
across plugin reload, and verify the installed commit/version after the command.
Never restart the engine or WebUI to update the plugin. Status polling stays local.

Use compact service rows for strix-llama.cpp and Open WebUI. Each row combines
name, installed version/state, and relevant shared action buttons: Install when
missing, Start/Stop, Open, Check, and Update when applicable. Busy state and
update feedback belong to that service, not a global banner. A running service
keeps its stop-before-update warning visible while an update is available.

Keep GTT on a compact row with live used/maximum, the supported ceiling choices
(64 / 96 / 110), and contextual **Change pending reboot** status. Choices must
be constrained by actual host memory; never assume a 128 GB machine. Changes
require confirmation, explain privileged boot-file changes, and never reboot.

### Models

Place the direct-GGUF link field and Add button above the model rows. Keep
catalog rows visible even when they do not fit. Use columns **Model**, **Status**,
**Params**, **Size**, **RAM**, and **Actions**. Put quant/recommendation under the
model name and fit/progress notes beneath the row. Do not repeat a redundant
engine column: every row uses the same engine. Provide explicit **buttons** for
Install, Load, Unload, and Delete as appropriate.
Actions must not be bare clickable text.

Use row-specific pending state, inline confirmation with Cancel for replacement
loads/deletion, and persistent, dismissible error feedback. A poll must not
erase an error or confirmation. Dismissing feedback does not cancel a job or
change service/model state. Report missing measurements as unavailable, not zero.

Clamp panel dimensions to the available screen. Keep controls reachable through
scrolling and responsive layout, including narrow screens and large fonts.
Long model names or errors must wrap/elide without covering actions. Provide
keyboard focus/activation and an Escape path; verify keyboard behavior rather
than promising unimplemented shortcuts. Verify light and dark themes.

The pill stays compact: GTT usage/ceiling, a loaded model's short name, and an
inference mark when the backend confirms processing. Do not replace the existing
local-models pill until explicitly approved.

## Model lifecycle and evidence

Weights live in `~/models`; recipe paths are relative and must stay contained
there. User-added links go into per-user configuration, not the shipped catalog.
Add accepts one complete HTTPS GGUF file (including a recognized Hugging Face
file-page conversion), not a repository URL or one split shard. Add may inspect
remote metadata but must not fetch weights or load a model.

Install downloads the recipe's required files, with real bytes/progress and
hash validation where a trusted hash exists. A locally computed hash for an
arbitrary link is not publisher authentication. Catalog file URLs use immutable
Hugging Face revisions; expected sizes and SHA-256 values were matched against
remote file metadata during cleanup without downloading the weights. That does
not prove a load/completion on the pinned engine. The retained recipes do not
have repository-recorded load/completion acceptance evidence; treat them as
unverified on that pin until the release gate is met. Existing-file integrity
handling still needs end-to-end acceptance, not just size checks.

Load requires installed files and a conservative fit check against the live GTT
ceiling: weight + recipe KV estimate + desktop reserve. Unknown memory fails
closed. This is an estimate, not a guarantee against OOM. Changing models requires
confirmation before unloading the current one. Load uses `/props?model=`;
unload uses `/models/unload` and waits for observed completion. Polls using
`/slots` or `/metrics` must include `autoload=false` so they cannot reload a model.

Delete confirms scope, unloads that model before removal, and preserves unrelated
files/projectors/sidecars. It must not restart the engine to delete another row.
Optional vision/projector/draft files remain off unless explicitly selected.
Image generation and automatic model discovery/loading are out of scope.

`catalog.json` owns recipe details; do not duplicate model-size tables in docs.
New recipes require a real load and completion on Strix Halo with recorded
hardware, engine commit, context, and date. Public speed claims additionally
require reproducible measurement evidence. Undated legacy speed records have
been removed pending such benchmarks; do not reintroduce them as claims.
Lifetime token accounting is not a completed feature; show only counters the
engine actually exposes, with their reset/availability limitations.

## Project boundaries

No root-running plugin, silent setup on add/update, automatic download or load,
global Vulkan overrides, unrelated application control, or automatic reboot.
The repo is canonical documentation. Version/release procedure belongs only in
[docs/releasing.md](docs/releasing.md); no historical development cut is treated
as a published release.
