# OmaStrix — agent contract

Read this before changing the machine or the plugin. The spec is `DESIGN.md`. If this file and `DESIGN.md` disagree, fix the stale one in the same change. Do not keep a second spec outside the repo.

Install id: `silexmachina.omastrix`. Private repo: https://github.com/SilexMachina/omastrix. No release. Do not run `omarchy plugin add` against this repo. Do not publish it, and do not tag it, until SilentD says so. The first tag is cut 0.5.

## What is running

OmaStrix is on the bar beside `silentd.local-models`. Do not remove either pill until he says swap. The slot is `~/.config/omarchy/plugins/silexmachina.omastrix`, a symlink to this repo. A QML change needs `omarchy restart shell`. Open the panel with `omarchy-shell silexmachina.omastrix open`. `shell call` on that id returns unknown.

The panel is two bordered panes. The title is OmaStrix. The line under it is Local AI for Strix Halo.

System pane: strix-llama.cpp installed / version / status, GTT boxes, Start, Stop, Open engine UI, Check for updates, Update. Then Open WebUI installed / version / status, Install, Start, Stop, Open, Check for updates, Update.

Model pane: a link field, then one table. Columns: Model, Status, Parameters, Size, RAM, Engine, Notes, Action. Status words are only Inferring, Loaded, Not Loaded, and Not Installed. Show every catalog row. A model that does not fit stays in the table. Notes state the shortfall. Load stays refused.

`bin/omastrix snapshot` is the live state. Read it before claiming a model is loaded, a download finished, a version, or a GTT number.

## Engine

One engine: native `halo-box/strix-llama.cpp`, Vulkan RADV. Not Docker, Ollama, stock `ggml-org/llama.cpp`, or `sero.local-ai`.

The first-install pin is `engine-pin.json`. A fresh install builds that commit. It does not build floating `main`. Upstream `v*` tags are a different line. Update compares the installed build number to the newest published Halo tag (`b` plus digits) and installs that tag when he clicks Update.

This machine may already be past the pin. Read `~/.config/omastrix/engine.json` for the installed commit and version. Do not downgrade it to the pin, and do not rewrite `engine-pin.json`, unless he says that newer build is the first-install version.

The product binary is `~/.local/share/omastrix/bin/llama-server`. Do not call `PATH` `llama-server`, `~/src/strix-llama.cpp`, or `llama-router-start`. RADV is set only in `~/.config/omastrix/llama.env`, sourced by that wrapper. Do not export `VK_DRIVER_FILES` session-wide.

User service `omastrix-llama`. Loopback only: `127.0.0.1:8080`. Start passes no model path, plus `--models-max 1 --models-preset ~/.config/omastrix/models.ini --offline`. The preset has no load-on-startup. Logon start stays off until he turns it on. Do not enable linger. Do not start or restart that service unless he asked. A restart drops the loaded model.

The panel button that says Install strix-llama.cpp is not wired. The installer is `bin/omastrix-engine-install`. Update is wired, and it refuses while the service is running.

## Library

Library root is `~/models`. Do not move weights into `~/.local/share/omastrix`. Do not pass `--models-dir ~/models`. The shipped list is `catalog.json`. The generated preset is `~/.config/omastrix/models.ini`.

Download does not load. Load is `GET /props?model=` after a fit check. Unload is `POST /models/unload`, then wait until `GET /models` says it is gone. Do not call `POST /models/load`.

Status polls must pass `autoload=false`. `GET /slots?model=` and `GET /metrics?model=` load the named model while autoload is on. That poll was reloading a model the moment Unload stopped it.

Delete is a second click. It removes that row's catalog files from `~/models` and leaves other files in the same folder, including a vision projector or an MTP file. If that model is loaded, the second click unloads it first. Do not restart the engine while a different model is loaded.

Add model takes a direct https link to one complete `.gguf` file. A Hugging Face file page with `/blob/` is rewritten to the download link. A model page, a repo link, and one piece of a split model are refused. Add puts a row in `~/.config/omastrix/added.json`. It does not download and it does not load. Install downloads. While a download is running, the row shows a bar and the bytes on disk versus the file size. Do not invent a percent.

Do not add a vision projector or an image-generation model as a catalog row. Seeing an image is `--mmproj` on an existing text recipe, off until he asks. Generating an image is not this engine.

## Open WebUI

OmaStrix has its own copy under `~/.local/share/omastrix/webui`. Settings: `~/.config/omastrix/webui.env`. User service: `omastrix-webui`. Signup is off. It listens on `0.0.0.0:3000`. llama stays on `127.0.0.1:8080`.

The hand install at `~/.local/share/open-webui` and `~/.local/bin/open-webui-serve` is this PC. Do not start it, stop it, or read its secret. Do not copy that secret into the product env.

Check for updates names the newest stable version on PyPI. Update installs that version into the OmaStrix copy when the service is stopped. It does not start the program. The warning stays on the panel while it is running.

## GTT

Choices are 64, 96, and 110 GB. `bin/omastrix set-gtt` writes the Limine drop-in and modprobe file, then `limine-mkinitcpio`, via `pkexec`. It does not reboot. While the configured ceiling differs from the live session, the panel says `GTT Change Pending Reboot`. Do not offer 118. Do not set `amd_iommu=off`. Do not copy this machine's ceiling onto a smaller Strix Halo.

## Do not

- Install Docker, Ollama, LM Studio, or a second engine.
- Bind llama-server to `0.0.0.0`.
- Enable linger, or start a service to prove a button.
- Click Install, Load, Unload, Delete, Add model, or Update from an agent turn unless he asked for that click.
- Poll a model-scoped route without `autoload=false`.
- Publish a speed number without the machine, context, and date.
- Set a global git identity. This repo's local identity stays as it is.
- Treat the October 2026 copy of this file as current. That copy said the engine was not installed. That was the first cut.
